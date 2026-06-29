# Phase 6.2 引き継ぎメモ（最終 Handoff）

## サマリ

README とリリース準備（Phase 6.2）を実装した。本フェーズがプロトタイプの最終サブステップである。

実装内容：
1. `scripts/setup.ps1` を完成（Node.js チェック追加、npm install 追加、%APPDATA% ディレクトリ作成、完了ガイダンス）
2. `README.md` を全面整備（Windows ユーザー向けクイックスタート、GCP セットアップ、トラブルシューティング、開発者セクション）
3. `docs/limitations.md` を新規作成（全フェーズ handoff の「保留」「未解決」項目を集約）
4. `LICENSE` を新規作成（MIT ライセンス）

バックエンドテスト総数：**133 件（全 PASS）**（Phase 6.1 から変化なし）
フロントエンドテスト総数：**50 件（全 PASS）**（Phase 6.1 から変化なし）

---

## 完成したプロトタイプの全体構成

```
プロトタイプ v0.1.0
├── バックエンド（FastAPI / Python 3.11+）
│   ├── Google OAuth2 認証（Phase 1.3）
│   ├── プロジェクト管理 CRUD（Phase 1.2, 2.1）
│   ├── Google Form 自動作成（Phase 2.2）
│   ├── 回答ポーリング・パース（Phase 2.3）
│   ├── ルール管理（Phase 3.1）
│   ├── CP-SAT スケジューラ（Phase 3.2, 3.3a, 3.3b）
│   ├── ドラフト保存・ロック管理（Phase 3.4）
│   ├── PDF 生成（ReportLab + Noto Sans JP）（Phase 5.1）
│   ├── PDF ダウンロード API（Phase 5.2）
│   └── RotatingFileHandler ログ設定（Phase 6.1）
│
├── フロントエンド（React + TypeScript / Vite）
│   ├── ホーム画面・プロジェクト一覧（Phase 4.1, 4.2）
│   ├── プロジェクト詳細画面・Form 作成 UI（Phase 4.3）
│   ├── 日程案表示・DnD 編集画面（Phase 4.4a, 4.4b）
│   ├── ドラフト保存・保存完了画面（Phase 4.4c）
│   ├── PDF ダウンロード UI（Phase 5.2）
│   └── ErrorBoundary（Phase 6.1）
│
├── スクリプト
│   ├── setup.ps1（初回セットアップ）（Phase 1.1 + 6.2 完成）
│   ├── start.ps1（本番モード起動）（Phase 4.1）
│   └── start-dev.ps1（開発モード起動）（Phase 4.1）
│
└── ドキュメント
    ├── README.md（Phase 6.2 全面整備）
    ├── docs/limitations.md（Phase 6.2 新規）
    ├── docs/e2e_test.md（Phase 6.1）
    └── docs/pdf_decisions.md（Phase 5.1）
```

---

## 採用方式の決定事項

### setup.ps1 の拡張

| 追加項目 | 内容 |
|---|---|
| Node.js バージョンチェック | `node --version` で 18 以上を確認、未インストールの場合はエラー終了 |
| フロントエンド npm install | `node_modules` が未存在の場合のみ `npm install` を実行（冪等） |
| %APPDATA% ディレクトリ作成 | `config`、`logs`、`data`、`projects` の 4 ディレクトリを作成 |
| 完了メッセージ | `oauth_client.json` 配置場所と `start.ps1` の実行を案内 |
| エラー時 | `Write-Error` + `exit 1` で終了コードを設定 |

### README.md の構成

- クイックスタート（5 ステップ: clone → setup.ps1 → oauth_client.json 配置 → start.ps1 → ブラウザ）
- 詳細 GCP セットアップ（既存の詳細手順を整理）
- 起動方法（本番モード / 開発モード）
- データディレクトリ構成
- トラブルシューティング
- E2E 確認手順へのリンク（`docs/e2e_test.md`）
- 制限事項へのリンク（`docs/limitations.md`）
- 開発者向け（テスト実行、コード構成、主要 API 一覧）
- ライセンス（MIT + Noto Sans JP OFL アトリビューション）

### limitations.md の構成

全フェーズ handoff の「保留」「未解決」「要確認」項目を以下の 10 カテゴリに整理：

1. シングルユーザー・シングルテナント前提
2. ファイルベースのローカル DB（JSON）の制限
3. Google Forms API のレート制限・ポーリング間隔
4. スケジューラの解最適性（CP-SAT 近似）
5. PDF の制限（フォントサイズ縮小、status 遷移未実装等）
6. OAuth・認証の制限
7. エラーリカバリの粒度
8. フロントエンドの制限（再スケジューリング時の DnD 状態消失等）
9. Windows 固有の制限
10. 将来拡張が必要な項目（requirements.md §9 より）

---

## 最終コミットハッシュ

```
docs(phase6.2): add final handoff memo  ← 本ドキュメント追加後
b5986942  chore(phase6.2): add setup.ps1 improvements, README, limitations, and LICENSE
```

タグ:
- `phase6.2-done` → handoff memo コミット
- `v0.1.0-prototype` → 同上（プロトタイプ完成マーク）

---

## 主要な実装上のパラメータ・決定

| 項目 | 値 | 備考 |
|---|---|---|
| ライセンス | MIT | プロジェクト本体のコード |
| フォントライセンス | SIL OFL 1.1 | `backend/app/fonts/OFL.txt` に全文 |
| setup.ps1 Node.js 最低バージョン | 18+ | requirements.md §1.4「Node.js 18+ (LTS推奨)」に準拠 |
| バックエンドテスト総数 | **133 件** | 変化なし（Phase 6.1 より） |
| フロントエンドテスト総数 | **50 件** | 変化なし（Phase 6.1 より） |

---

## 追加・変更したファイル

### 新規
- `docs/limitations.md`: 全フェーズの制限事項集約
- `LICENSE`: MIT ライセンス

### 変更
- `scripts/setup.ps1`: Node.js チェック・npm install・%APPDATA% ディレクトリ作成・完了ガイダンス追加
- `README.md`: Windows ユーザー向けに全面整備

---

## 既知の制限事項（抜粋・重要度高）

`docs/limitations.md` に詳細を記載しているが、特に重要なものを抜粋する。

1. **PDF 保存場所**: `%APPDATA%\...\output\` への PDF 自動保存は未実装。ブラウザのダウンロードフォルダに保存される。
2. **プロジェクト status の `finalized` 遷移**: PDF ダウンロード後も status は `draft_saved` のまま。
3. **再編集時の DnD 状態消失**: 「再編集」→ `SchedulePage` 遷移時にスケジューリングが再実行され、前回の DnD 編集内容が失われる。
4. **ポーリングのブロッキング**: 回答同期（`POST /responses/sync`）はバックエンドをブロックする同期処理。

---

## 今後の拡張ポイント

本プロトタイプを実運用向けに拡張する場合の主要ポイント：

### 短期（プロトタイプの改善）

1. **PDF output\\ 保存**: PDF 生成時に `output/` ディレクトリへの自動保存を追加
2. **finalized 状態遷移**: PDF ダウンロード成功時に `status = finalized` へ遷移
3. **再編集時の DnD 状態保持**: `GET /drafts/latest` で既存ドラフトを読み込んで表示
4. **各 API ルータへのロギング追加**: `logging.getLogger(__name__)` と `logger.info(...)` の呼び出しを追加（Phase 6.1 handoff より）

### 中期（機能追加）

5. **過去ドラフトのクリーンアップ**: `drafts/` フォルダ内の古いファイルを自動削除するメンテナンス機能
6. **非同期ポーリング**: `POST /responses/sync` を非同期化して API サーバのブロッキングを解消
7. **生徒氏名表示**: 出席番号 → 氏名のマッピングマスタとその表示

### 長期（アーキテクチャ変更）

8. **DB 化**: JSON ファイルから SQLite / PostgreSQL への移行（Repository 抽象化済みのため差し替え可能）
9. **マルチテナント対応**: 学校単位のテナント管理
10. **macOS / Linux 対応**: PowerShell スクリプトを bash に置き換え、パス操作を整理

---

## Phase 6.2 完了

本ドキュメントをもって Phase 6.2（README とリリース準備）の実装を完了とし、
プロトタイプ v0.1.0 のすべてのフェーズ（Phase 1.1 〜 6.2、全 22 サブステップ）が完了した。
