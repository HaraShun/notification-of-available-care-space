# notification-of-available-care-space

指定したWebページの予約表で、指定日時に空きが出たら [ntfy.sh](https://ntfy.sh) でスマホ Push 通知する GitHub Actions ジョブ。

## セットアップ

### 1. ntfy アプリ

- スマホに [ntfy](https://ntfy.sh/app) アプリを入れる（iOS/Android）
- 推測されにくいトピック名を決め（例: `care-home-watch-x7k2q9`）、アプリで購読

### 2. 監視対象を Google スプレッドシートで管理

公開（リンクを知っている全員に閲覧権限を付与）したスプレッドシートに、以下の形式で監視したい日時を記入。

| date | time_zone |
| --- | --- |
| 2026/04/11 | 12-15 |
| 2026/04/12 | 9-12 |
| 2026/04/12 | 12-15 |

- 1行目はヘッダ（中身は何でもOK、スキップされます）
- `date` は `YYYY/MM/DD` 形式
- `time_zone` は `9-12` / `12-15` / `15-18` のいずれか
- 行を追加・削除するだけで監視対象を変更できます（コミット不要）

### 3. リポジトリの Settings → Secrets and variables → Actions

#### Variables
| 名前 | 例 | 説明 |
| --- | --- | --- |
| `TARGET_URL` | `https://www.care-home.com/yoyaku.html` | 監視対象ページ |
| `WATCH_SHEET_URL` | `https://docs.google.com/spreadsheets/d/XXX/edit#gid=0` | 監視日時シートのURL（通常の編集URLでOK） |

#### Secrets
| 名前 | 例 |
| --- | --- |
| `NTFY_TOPIC_URL` | `https://ntfy.sh/care-home-watch-x7k2q9` |

> トピック名を知っている人は誰でも通知を読めるため、URLは Secret 管理推奨。

## 動作
- `.github/workflows/check.yml` が30分おきに `check_availability.py` を実行
- ページの予約表テーブルを解析（`thead` の時間帯ヘッダ × `tbody` の利用日行）し、指定の日時セルが `○` / `〇` / `△` なら ntfy で Push 通知
- 監視対象ページは**直近30日分しか掲載されない**。それより先の日付をシートに書いておくのは問題なく（ページ取得は1回だけなので追加コストなし）、掲載され次第そのまま照合が始まる。ログには `サイト未掲載 (表示範囲 ...外)` と出る
- 逆に、表示範囲内なのに引けない行は `★該当セルなし` と出る。日付や時間帯の書式ミスを疑う
- 注意: 状態保持はしていないため、空きが続く間は30分おきに通知が飛びます