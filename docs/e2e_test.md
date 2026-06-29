# E2E 動作確認手順

本書は「保護者面談調整ツール」の End-to-End（E2E）動作確認手順書です。  
ユーザー（実装者本人）が手動で実施する確認ケースを記載します。

---

## 前提

### 環境

- Windows 10 / 11
- Python 3.11+ / venv 設定済み（`backend\.venv`）
- Node.js 18+ LTS
- Google Chrome / Microsoft Edge（最新版推奨）

### 必要ファイルの配置

| ファイル | 配置先 | 備考 |
|---|---|---|
| `oauth_client.json` | `%APPDATA%\meeting-scheduler\config\oauth_client.json` | GCP からダウンロードした OAuth2 クライアント情報 |
| `ipaexg.ttf` | `backend\app\fonts\ipaexg.ttf` | PDF 日本語フォント（IPAex ゴシック） |

`%APPDATA%` は通常 `C:\Users\<ユーザー名>\AppData\Roaming` を指します。

### GCP の OAuth 同意画面設定（重要）

GCP コンソール（https://console.cloud.google.com/）の **「APIとサービス」→「OAuth 同意画面」** で以下を確認してください。

| 項目 | 推奨値 | 備考 |
|---|---|---|
| ユーザータイプ | **外部** | 個人 Gmail を使うため |
| 公開ステータス | **テスト** | 本番未確認のままだと一般ユーザーは利用不可 |
| テストユーザー | **認証に使う Gmail アドレスを追加** | 未登録だと「アクセスをブロック: ...は Google の審査プロセスを完了していません」と表示される |
| 必須スコープ | `forms.body` / `forms.responses.readonly` / `drive.file` | コードと一致させる |

### GCP の OAuth クライアント（リダイレクト URI）

「APIとサービス」→「認証情報」→ 該当の OAuth 2.0 クライアント ID で、
**承認済みのリダイレクト URI** に以下を登録：

```
http://localhost:8000/api/auth/google/callback
```

未登録だと Google 側で `redirect_uri_mismatch` エラーになります。

---

## 起動手順

### 開発モード起動（2 プロセス並列）

**ターミナル 1 — バックエンド:**

```powershell
cd <project-root>\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

起動確認:
```
INFO:     Application startup complete.
```

ログファイル: `%APPDATA%\meeting-scheduler\logs\app.log`

**ターミナル 2 — フロントエンド:**

```powershell
cd <project-root>\frontend
npm run dev
```

起動確認:
```
  ➜  Local:   http://localhost:5173/
```

ブラウザで `http://localhost:5173` にアクセスします。

---

## 実機テストケース

以下のケースを順番に実行します。

---

### ケース a: プロジェクト作成

1. ホーム画面（`/`）を開く
2. 「面談調整開始」ボタンをクリック
3. プロジェクト名（例: `3年A組 7月面談`）・候補日・時間枠・出席番号を入力して作成

**期待結果:**
- プロジェクト詳細画面（`/projects/:id`）に遷移する
- ホーム画面に戻ると一覧に作成したプロジェクトが表示される
- `%APPDATA%\meeting-scheduler\projects\<project_id>\project.json` が生成される

---

### ケース b: Google Form 作成・回答 URL 取得

1. プロジェクト詳細画面で「候補日程聴取用 Google Form 作成」ボタンをクリック
2. Google OAuth 認証画面でアカウント認証する（初回のみ）
3. 認証完了後、Form URL が画面に表示される
4. URL 横のコピーボタンで URL をクリップボードにコピーする

**期待結果:**
- Form URL（`https://forms.gle/...`）が表示される
- Google Forms でフォームが作成される
- ログ（`app.log`）に Form 作成成功のログが記録される

---

### ケース c: 回答ポーリング → 学生取り込み

1. コピーした Form URL をブラウザで開く
2. 出席番号と希望日時を選択して送信（複数の出席番号で繰り返す）
3. プロジェクト詳細画面に戻り「最新回答を取得」ボタンをクリック

**期待結果:**
- 受領済み出席番号一覧が更新される
- `%APPDATA%\meeting-scheduler\projects\<project_id>\responses\<出席番号>\<timestamp>.json` が生成される
- 未受領出席番号一覧から回答済み生徒が消える

---

### ケース d: ルール設定

1. プロジェクト詳細画面で「ルールカスタマイズ」ボタンをクリック
2. 連続コマ数上限・教師不可時間帯・ソフト制約（ペアリング等）を設定して保存

**期待結果:**
- `%APPDATA%\meeting-scheduler\projects\<project_id>\rules.json` が更新される
- 設定内容が画面に反映される

---

### ケース e: スケジューリング実行 → マトリクス表示

1. プロジェクト詳細画面で「面談日程案作成」ボタンをクリック
2. スケジューリングが実行され日程案表示画面（`/projects/:id/schedule`）に遷移する

**期待結果（解あり）:**
- 日付 × 時間枠のマトリクスに出席番号が表示される
- 未配置生徒がいない場合、未配置リストは空

**期待結果（解なし）:**
- 画面上部に「違反制約」一覧が表示される
- 未配置生徒の出席番号一覧が表示される

---

### ケース f: DnD で枠入れ替え

1. 日程案表示画面でドラッグ可能な生徒カードを別のスロットへドラッグ＆ドロップする

**期待結果（候補日時内への移動）:**
- スロットの割り当てが入れ替わる
- 警告ダイアログは表示されない

**期待結果（候補日時外への移動）:**
- スロットの割り当ては更新される
- 「候補日時外に移動しました」の警告ダイアログが表示される
- ダイアログを閉じると編集状態が保持される

---

### ケース g: ドラフト保存 → 保存完了画面

1. 日程案表示画面で「保存」ボタンをクリック

**期待結果:**
- 保存完了画面（`/projects/:id/saved`）に遷移する
- 「日程案が保存されました。」が表示される
- `%APPDATA%\meeting-scheduler\projects\<project_id>\drafts\draft_<timestamp>.json` が生成される
- JSON の `"locked": true` になっている

---

### ケース h: PDF ダウンロード → PDF 確認

1. 保存完了画面で「PDF出力」ボタンをクリック

**期待結果:**
- PDFファイルがダウンロードされる（例: `schedule_<project_id>.pdf`）
- ダウンロードした PDF を開くと A4 縦・マトリクス形式のスケジュール表が表示される
- 日本語（出席番号・日付・時刻）が文字化けなく表示される
- `%APPDATA%\meeting-scheduler\projects\<project_id>\output\` に PDF が保存される

---

### ケース i: 再編集 → 再スケジューリング

1. 保存完了画面で「再編集」ボタンをクリック

**期待結果:**
- ドラフトのロックが解除される（`"locked": false`）
- 日程案表示画面に戻り、スケジューリングが再実行される
- 新たな DnD 編集 → 保存 → PDF 出力が可能な状態になる

---

## 各ステップの確認観点

### 成功時

| 確認項目 | 確認方法 |
|---|---|
| 正常な画面遷移 | ブラウザの URL とページ内容を目視確認 |
| ファイル生成 | エクスプローラーで `%APPDATA%\meeting-scheduler\` を確認 |
| ログ出力 | `%APPDATA%\meeting-scheduler\logs\app.log` をテキストエディタで確認 |
| PDF 内容 | ダウンロードした PDF を Adobe Acrobat / Microsoft Edge で開いて確認 |

### エラー時の確認観点

| HTTP ステータス | 症状 | 確認方法 |
|---|---|---|
| 400 Bad Request | OAuth state 不一致（CSRF 対策） | ブラウザをリロードして OAuth フローをやり直す |
| 401 Unauthorized | 未認証またはトークン期限切れ | 「Google でログイン」から再認証 |
| 404 Not Found | プロジェクト ID 不在 / ドラフト未保存 | エラーメッセージ（`detail` フィールド）を画面で確認 |
| 409 Conflict | ドラフトが既にロック済みで再保存しようとした | 画面に「すでにドラフトが保存されています。再編集するにはアンロックが必要です。」が表示される |
| 500 Internal Server Error | サーバー側例外 | `app.log` を確認してスタックトレースを特定 |
| フロント例外 | 予期しないエラーで ErrorBoundary が発動 | 「エラーが発生しました。ページを再読み込みしてください。」が表示される |

---

## ログ確認

アプリケーションログは以下に出力されます。

```
%APPDATA%\meeting-scheduler\logs\app.log
```

ローテーション設定: 10 MB / 最大 5 世代

ログ例:
```
2026-07-01T12:00:00 INFO     app.api.projects プロジェクト作成: project_id=abc123
2026-07-01T12:01:00 INFO     app.api.forms Google Form 作成完了: form_id=XXXXXX
2026-07-01T12:02:00 ERROR    app.api.pdf PDF生成エラー: フォントファイルが見つかりません
```

---

## 実機確認結果

> この欄はユーザーが手動確認後に記録してください。

| ケース | 実施日 | 結果 | 備考 |
|---|---|---|---|
| a. プロジェクト作成 | | | |
| b. Form 作成・URL 取得 | | | |
| c. 回答ポーリング | | | |
| d. ルール設定 | | | |
| e. スケジューリング | | | |
| f. DnD 入れ替え | | | |
| g. ドラフト保存 | | | |
| h. PDF ダウンロード | | | |
| i. 再編集 | | | |
