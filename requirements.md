# 保護者面談調整ツール 要件定義書（プロトタイプ）

## 0. ドキュメント目的

本書は、中学校教師を想定ユーザーとした保護者面談調整ツールのプロトタイプ実装を、Claude Code に依頼するための要件定義書である。限定的なユーザーによる試用を目的とし、将来的なバックエンド化・マルチテナント化を見据えた構成とする。

---

## 1. プロトタイプ前提と非機能要件

### 1.1 スコープ

- 限定的な教師ユーザーによる試用を目的としたプロトタイプ
- 教師PC上でローカル起動するWebアプリとして実装
- 1教師1インスタンス（シングルテナント）

### 1.2 将来拡張の方向性（プロトタイプでは未実装）

| 観点 | プロトタイプ | 将来 |
|---|---|---|
| データ保管 | 教師PCローカル（ファイルベース） | 専用バックエンド |
| テナント | 教師単位 | 学校単位 |
| プロジェクト実体 | ローカルディレクトリ | DBレコード |
| 受領検知 | 定期ポーリング | Pub/Sub等のプッシュ |

プロトタイプ実装時も、データアクセス層を抽象化し将来のDB移行を容易にすること。

### 1.3 個人情報の取り扱い

- 生徒氏名・連絡先等の個人情報はマスタとして保有しない
- 生徒の識別は**出席番号**で行う
- 生徒へのForm URL配信は本ツールでは行わず、教師が手動でコピーして配布する

---

## 2. 技術スタック

| レイヤ | 採用技術 |
|---|---|
| バックエンド | Python 3.11+ / FastAPI |
| フロントエンド | React + TypeScript（Vite ビルド） |
| スケジューリング | OR-Tools (Python) |
| Google連携 | Google Forms API / Google Drive API（OAuth2） |
| データ保管 | ローカルファイルシステム（JSON） |
| PDF生成 | ReportLab または WeasyPrint |
| 起動方式 | `localhost:<port>` でブラウザアクセス |

### 2.1 認証

- 教師個人のGoogleアカウントでOAuth2認証
- 必要スコープ：
  - `https://www.googleapis.com/auth/forms.body`
  - `https://www.googleapis.com/auth/forms.responses.readonly`
  - `https://www.googleapis.com/auth/drive.file`
- 教師自身のGoogle Drive配下にFormが作成される

### 2.2 起動方式

- バックエンドとフロントエンドを単一プロセスから起動（FastAPIが静的ビルド済みフロントを配信）
- 起動コマンド一発で `http://localhost:<port>` にアクセス可能とする

---

## 3. データモデルとファイル構成

### 3.1 ディレクトリ構造

```
<APP_DATA_ROOT>/
├── config/
│   ├── oauth_token.json          # Google OAuth2 トークン
│   └── global_rules.json         # ホーム画面で設定する既定ルール
└── projects/
    └── <project_id>/
        ├── project.json          # プロジェクトメタ情報
        ├── rules.json            # 当プロジェクトでカスタマイズされたルール
        ├── form.json             # 作成したGoogle Formのメタ情報
        ├── responses/
        │   └── <出席番号>/
        │       ├── 20260624_153012.json
        │       └── 20260625_091045.json   # 最新を採用
        ├── drafts/
        │   └── draft_<timestamp>.json     # 面談日程ドラフト
        └── output/
            └── schedule_<timestamp>.pdf
```

`<APP_DATA_ROOT>` は OS の標準アプリデータディレクトリ配下（例：macOSなら `~/Library/Application Support/<アプリ名>/`）。

### 3.2 主要データスキーマ

#### project.json

```json
{
  "project_id": "2026-Q3-class-A",
  "display_name": "3年A組 7月面談",
  "created_at": "2026-06-24T10:00:00+09:00",
  "status": "in_progress | draft_saved | finalized",
  "slot_minutes": 20,
  "candidate_dates": ["2026-07-15", "2026-07-16", "2026-07-17"],
  "candidate_time_slots": [
    {"start": "16:00", "end": "16:20"},
    {"start": "16:20", "end": "16:40"}
  ],
  "student_numbers": [1, 2, 3, 4, 5]
}
```

#### responses/<出席番号>/<timestamp>.json

```json
{
  "project_id": "2026-Q3-class-A",
  "student_number": 15,
  "submitted_at": "2026-06-24T15:30:12+09:00",
  "google_form_response_id": "ABCDEF...",
  "availability": [
    {"date": "2026-07-15", "start": "16:00", "end": "16:20"},
    {"date": "2026-07-15", "start": "16:20", "end": "16:40"},
    {"date": "2026-07-16", "start": "17:00", "end": "17:20"}
  ]
}
```

#### rules.json（プロジェクト個別ルール）

```json
{
  "global_constraints": {
    "max_consecutive_slots": 3,
    "forced_break_slots": 1,
    "max_slots_per_day": 10,
    "teacher_unavailable": [
      {"date": "2026-07-16", "start": "18:00", "end": "19:00"}
    ]
  },
  "student_constraints": [
    {
      "type": "pairing",
      "student_numbers": [5, 12],
      "weight": 8
    },
    {
      "type": "avoid_time",
      "student_number": 7,
      "avoid_after": "18:00",
      "weight": 5
    },
    {
      "type": "prefer_time",
      "student_number": 3,
      "prefer_before": "17:00",
      "weight": 5
    },
    {
      "type": "duration_multiplier",
      "student_number": 9,
      "multiplier": 2
    }
  ]
}
```

#### drafts/draft_<timestamp>.json

```json
{
  "project_id": "2026-Q3-class-A",
  "saved_at": "2026-06-24T20:00:00+09:00",
  "locked": true,
  "assignments": [
    {"student_number": 15, "date": "2026-07-15", "start": "16:00", "end": "16:20"}
  ],
  "unassigned_students": [22],
  "violated_constraints": []
}
```

---

## 4. 機能要件

### 4.1 画面遷移

```
ホーム画面
├─[面談調整開始]→ プロジェクト画面（新規作成）
├─[過去プロジェクト]→ プロジェクト画面（再オープン）
└─[ルール設定]→ グローバルルール設定画面

プロジェクト画面
├─[候補日程聴取用Form作成]→ Form作成完了表示（URL表示・コピー）
├─[最新回答を取得]→ 受領状況更新
├─[ルールカスタマイズ]→ プロジェクトルール設定画面
└─[面談日程案作成]→ 日程案表示画面

日程案表示画面
├─（ドラッグで手修正）
└─[保存]→ 保存完了画面（ドラフトロック）

保存完了画面
├─[PDF出力]→ PDFダウンロード
└─[再編集]→ ロック解除し日程案表示画面へ
```

### 4.2 ホーム画面

- 「面談調整開始」ボタン → 新規プロジェクト作成（プロジェクトIDと表示名を入力）
- 過去プロジェクト一覧（作成日時降順、ステータス表示）→ クリックで再オープン
- 「ルール設定」ボタン → グローバルルール設定画面

### 4.3 プロジェクト画面

- プロジェクトメタ情報の表示・編集（候補日、時間枠定義、出席番号リスト）
- 「候補日程聴取用Google Form作成」ボタン
  - 候補日 × 時間枠のチェックボックスマトリクスを持つFormを生成
  - 質問項目：出席番号（必須・整数）、候補日時枠（チェックボックスマトリクス）
  - 生成完了後、Form URLを画面表示しコピーボタンを併設
- Form受領状況表示
  - 受領済み出席番号一覧
  - 未受領出席番号一覧
  - 「最新回答を取得」ボタン（手動ポーリング）
- 「ルールカスタマイズ」ボタン → プロジェクト個別ルール編集
- 「面談日程案作成」ボタン → スケジューリング実行

### 4.4 Form回答受領

- ポーリング方式：プロジェクト画面が開かれている間、N秒間隔（既定60秒）でForms APIを呼び出し
- 手動取得：「最新回答を取得」ボタンで即時実行
- 新規回答検知時、`responses/<出席番号>/<受信時刻>.json` に保存
- 同一出席番号から複数回答があった場合、すべて別ファイルとして保存し、後続処理ではファイル名タイムスタンプ最新のものを使用

### 4.5 ルール設定

#### 4.5.1 グローバルルール設定画面（ホーム画面から）

- プロジェクト作成時に既定値として複製される
- 編集項目は 3.2 の rules.json 構造に準ずる

#### 4.5.2 プロジェクトルール設定画面

- グローバルルールを複製した状態から開始
- 制約種別は以下のプリセットから追加・編集・削除
  - 連続コマ数上限 / 強制空きコマ数（グローバル）
  - 1日あたりコマ数上限（グローバル）
  - 教師不可時間帯（グローバル）
  - ペアリング（出席番号同士を連続枠に）
  - 時間帯回避（特定出席番号が特定時刻以降/以前を避ける）
  - 時間帯優先（特定出席番号が特定時刻以前/以降を優先）
  - 所要時間倍率（特定出席番号が複数コマを使用）
- ソフト制約は重み（0〜10）を指定

### 4.6 面談日程案作成（スケジューリング）

#### 4.6.1 入力

- 受領済み回答（出席番号ごとの最新ファイル）
- プロジェクトルール

#### 4.6.2 制約分類

| 制約 | 区分 |
|---|---|
| 候補日時の範囲内であること | ハード |
| 教師不可時間帯の除外 | ハード |
| 1コマ1生徒 | ハード |
| 所要時間倍率（連続コマ確保） | ハード |
| 連続コマ数上限 / 強制空きコマ | ソフト |
| 1日あたりコマ数上限 | ソフト |
| ペアリング | ソフト |
| 時間帯回避・優先 | ソフト |

#### 4.6.3 アルゴリズム

- OR-Tools CP-SAT を使用
- ソフト制約は重み付きペナルティとして目的関数に加え、総ペナルティを最小化
- ハード制約で解なしの場合、緩和は行わず「解なし」として返す

#### 4.6.4 解なし時の挙動

- 違反している制約の一覧を表示
- 未配置となった生徒の出席番号一覧を表示
- 教師が候補日時を追加するか、ルールを緩めるかを判断できるよう情報提示

### 4.7 日程案表示画面

- 日付 × 時間枠のマトリクスを表示
- 各セルに割り当てられた出席番号入りオブジェクト
- ドラッグ&ドロップで入れ替え可能
- 移動先が当該生徒の候補日時に含まれない場合は警告表示（操作自体は許可）
- 解なし時は未配置生徒リストを画面上部に表示
- 「保存」ボタン → ドラフト保存＋ロック＋保存完了画面遷移

### 4.8 保存完了画面

- 「PDF出力」ボタン → 日程表PDFをダウンロード
  - A4縦
  - 複数日1ページのマトリクス形式
  - 各セルに出席番号
- 「再編集」ボタン → ドラフトのロック解除し日程案表示画面へ戻る

### 4.9 ドラフトの版管理

- 保存実行時に `draft_<timestamp>.json` として保存しロック
- 再編集時はロックを解除して既存ドラフトを上書き候補とする
- 過去ドラフトはファイルとして残置（参照は将来課題）

---

## 5. Google Forms 連携の実装方針

### 5.1 Form作成

- Google Forms API を直接呼び出して作成
- チェックボックスマトリクスの作成可否を実装前に確認すること
- マトリクスが API でサポートされていない場合、**代替実装**として「日付ごとに複数選択チェックボックス質問を並べる」形式に切り替える
- 質問項目：
  - 出席番号（必須・短文回答、整数バリデーション）
  - 候補日時枠（マトリクスまたは日付ごとの複数選択）

### 5.2 Form受領検知

- 定期ポーリング方式
- `forms.responses.list` API を呼び出し、未取得の `responseId` を抽出
- ポーリング間隔は設定可能（既定60秒）
- 手動「最新回答を取得」ボタンも提供
- プロジェクト画面非表示時はポーリング停止

---

## 6. API設計（バックエンド）

主要エンドポイントの目安。

| メソッド | パス | 用途 |
|---|---|---|
| GET | /api/projects | プロジェクト一覧 |
| POST | /api/projects | プロジェクト作成 |
| GET | /api/projects/{id} | プロジェクト詳細 |
| PUT | /api/projects/{id} | プロジェクトメタ更新 |
| POST | /api/projects/{id}/form | Google Form作成 |
| POST | /api/projects/{id}/responses/sync | 回答ポーリング実行 |
| GET | /api/projects/{id}/responses | 受領済み回答一覧 |
| GET | /api/projects/{id}/rules | プロジェクトルール取得 |
| PUT | /api/projects/{id}/rules | プロジェクトルール更新 |
| POST | /api/projects/{id}/schedule | スケジューリング実行 |
| POST | /api/projects/{id}/drafts | ドラフト保存（ロック） |
| POST | /api/projects/{id}/drafts/unlock | ロック解除 |
| GET | /api/projects/{id}/pdf | PDF生成・ダウンロード |
| GET | /api/global-rules | グローバルルール取得 |
| PUT | /api/global-rules | グローバルルール更新 |
| GET | /api/auth/google | OAuth認証開始 |
| GET | /api/auth/google/callback | OAuth コールバック |

データアクセスは Repository パターン等で抽象化し、ファイルベース実装を後でDB実装に差し替え可能にすること。

---

## 7. ディレクトリ構成（実装）

```
project-root/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPIエントリポイント
│   │   ├── api/                   # ルータ
│   │   ├── services/
│   │   │   ├── google_forms.py
│   │   │   ├── scheduler.py       # OR-Tools
│   │   │   ├── pdf_generator.py
│   │   │   └── polling.py
│   │   ├── repositories/          # データアクセス抽象化
│   │   │   └── file_repository.py
│   │   ├── models/                # Pydanticモデル
│   │   └── config.py
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   └── api/                   # バックエンドAPIクライアント
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

---

## 8. 想定外・将来課題（プロトタイプでは扱わない）

- 生徒へのForm URL自動配信
- 生徒氏名表示
- 兄弟関係マスタ（プロトタイプでは出席番号ペアを教師が手動指定）
- マルチテナント
- DB化
- 過去ドラフトの履歴比較UI
- 認証スコープ最小化の精査（プロトタイプでは drive.file で十分かを実装時確認）

---

## 9. 未確定・実装時確認事項

1. Google Forms API のチェックボックスグリッド対応状況（最新仕様確認）
2. Forms API のレスポンス JSON 構造の最新仕様（マトリクス回答のパース方法）
3. ポーリングAPIのクォータ制限（既定60秒間隔で問題ないか）
4. ローカルファイルパスのOS差異（Windows/macOS/Linux）
5. PDF日本語フォントの埋め込み手段
