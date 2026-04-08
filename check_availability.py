"""予約ページ 空き状況チェック → ntfy.sh Push 通知

環境変数:
  TARGET_URL       監視するページURL
  WATCH_SHEET_URL  監視日時を記入した Google スプレッドシートのURL
                   (通常の編集URL/共有URL/公開CSVのいずれでも可)
                   1列目=日付(YYYY/MM/DD), 2列目=時間帯ラベル
                   時間帯ラベルはページのテーブルヘッダ表記から数字部分だけ抽出して
                   "9-12" のような正規化形で照合する (例: "9-12", "12-15", "9時～12時" 等)
                   1行目はヘッダ扱いでスキップ
  NTFY_TOPIC_URL   ntfy トピックURL (例: https://ntfy.sh/your-secret-topic-name)
"""

import csv
import io
import os
import re
import sys
import unicodedata
import requests
from bs4 import BeautifulSoup

AVAILABLE_MARKS = {"○", "〇", "△"}
DATE_RE = re.compile(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})")


def normalize_zone(label: str) -> str:
    """全角→半角、空白除去後、数字ペアを抽出して "9-12" 形に正規化"""
    s = unicodedata.normalize("NFKC", label)
    nums = re.findall(r"\d+", s)
    if len(nums) >= 2:
        return f"{int(nums[0])}-{int(nums[1])}"
    return s.strip()


def normalize_date(text: str) -> str:
    """ "2026年04月10日（金）" → "2026/04/10" """
    s = unicodedata.normalize("NFKC", text)
    m = DATE_RE.search(s)
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{int(y):04d}/{int(mo):02d}/{int(d):02d}"


def to_csv_url(sheet_url: str) -> str:
    """通常のスプレッドシートURLをCSVエクスポートURLへ変換 (既にCSV URLならそのまま)"""
    if "/export?" in sheet_url and "format=csv" in sheet_url:
        return sheet_url
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sheet_url)
    if not m:
        return sheet_url
    sheet_id = m.group(1)
    gid_match = re.search(r"[?#&]gid=(\d+)", sheet_url)
    gid = gid_match.group(1) if gid_match else "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def fetch_watch_targets(sheet_url: str):
    """シートから [(date, normalized_zone), ...] を返す"""
    csv_url = to_csv_url(sheet_url)
    r = requests.get(csv_url, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    reader = csv.reader(io.StringIO(r.text))
    rows = list(reader)[1:]  # ヘッダスキップ
    targets = []
    for row in rows:
        if len(row) < 2:
            continue
        d, label = row[0].strip(), row[1].strip()
        if not d or not label:
            continue
        targets.append((normalize_date(d) or d, normalize_zone(label)))
    return targets


def fetch_availability(url: str):
    """ページのテーブルから {(date, normalized_zone): mark} を構築"""
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, "html.parser")

    table = soup.find("table")
    if table is None:
        return {}

    headers = [th.get_text(strip=True) for th in table.select("thead th")]
    # 先頭は「利用日」列、それ以外が時間帯ヘッダ
    zone_headers = [normalize_zone(h) for h in headers[1:]]

    result = {}
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        date = normalize_date(tds[0].get_text(strip=True))
        if not date:
            continue
        for zone_label, td in zip(zone_headers, tds[1:]):
            text = td.get_text(strip=True)
            mark = next((c for c in text if c in AVAILABLE_MARKS or c in {"×", "休"}), "?")
            result[(date, zone_label)] = mark
    return result


def check(availability, targets):
    hits = []
    for d, z in targets:
        mark = availability.get((d, z))
        if mark is None:
            print(f"  {d} {z}: (該当セルなし)")
            continue
        print(f"  {d} {z}: {mark}")
        if mark in AVAILABLE_MARKS:
            hits.append((d, z, mark))
    return hits


def notify(body: str):
    topic_url = os.environ["NTFY_TOPIC_URL"]
    r = requests.post(
        topic_url,
        data=body.encode("utf-8"),
        headers={
            "Title": "空き通知",
            "Priority": "high",
            "Tags": "baby",
        },
        timeout=30,
    )
    r.raise_for_status()
    print("ntfy sent:", r.status_code)


def main():
    url = os.environ["TARGET_URL"]
    sheet_url = os.environ["WATCH_SHEET_URL"]
    targets = fetch_watch_targets(sheet_url)
    print(f"URL={url}\nTargets={targets}")
    if not targets:
        print("ERROR: シートに監視対象がありません", file=sys.stderr)
        sys.exit(1)

    availability = fetch_availability(url)
    if not availability:
        print("ERROR: ページから空き情報を取得できません", file=sys.stderr)
        sys.exit(1)

    hits = check(availability, targets)
    if not hits:
        print("空きなし")
        return

    lines = [f"{d} {z}時: {m}" for d, z, m in hits]
    body = "【空きあり】\n" + "\n".join(lines) + f"\n{url}"
    print(body)
    notify(body)


if __name__ == "__main__":
    main()
