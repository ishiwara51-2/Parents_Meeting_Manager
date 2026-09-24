# ログイン状態ヘッダー表示 引き継ぎメモ（保留中）

## ステータス

**保留**。調査・方針決定までは完了したが実装は未着手。ユーザー指示により中断し、
別タスク（GoogleForm の「都合の良い日時」→「都合の悪い日時」変更）を優先して着手する。

## 依頼内容

「ログイン状態がページヘッダーでわかるようにして」

## 調査結果（重要）

1. `frontend/src/components/ui/AppShell.tsx` には `headerRight`（コメント:「認証バッジ等」）という
   ヘッダー右端スロットが既に用意されている。
2. しかし実際にこれを使っているのは **`HomePage.tsx` のみ**。他の7画面
   （ProjectNewPage / ProjectPage / ProjectRulesPage / GlobalRulesPage / SchedulePage / SavedPage）は
   ヘッダーにログイン状態を一切表示していない。
3. HomePage の実装自体もバグっている：
   - フロント型 `AuthStatus`（`frontend/src/api/types.ts:159`）と `authApi.status()`
     （`frontend/src/api/client.ts:80`）は `{ authenticated: boolean; email?: string }` を期待。
   - しかし実際のバックエンド `GET /api/auth/status`（`backend/app/api/auth.py:137-142`）は
     `{ "status": "authorized" | "unauthorized" }` を返しており、型と実体が一致していない。
   - 結果、`HomePage.tsx` の `authStatus?.authenticated` は常に `undefined`（falsy）になり、
     **実際にログイン済みでも常に「Googleでログイン」ボタンが表示される**バグになっている。
4. `email` は現状どこにも取得ロジックが存在しない。
   - `backend/app/services/google_auth.py` の `SCOPES` は
     `forms.body` / `forms.responses.readonly` / `drive.file` のみで、
     `openid` / `email` / `profile` は含まれていない。
   - `frontend/tests/HomePage.test.tsx` には `email: 'test@example.com'` を期待する
     TDD初期フェーズのテストがあるが、バックエンドはこれを満たせていない（未実装のまま残置）。

## ユーザーとの合意事項

`AskUserQuestion` で確認した結果：
- **全画面ヘッダーでログイン状態を表示する**（Home限定をやめ `AppShell` 側に一元化する方針）
- **メールアドレスも表示する**（認証済み/未認証だけでなく email も出す）

→ メールアドレス表示を実現するには OAuth スコープ追加（`openid` + `email` 等）と
**既存ユーザーの再同意（再ログイン）が必要**になる点は要ユーザー合意済み（質問時に選択肢として提示し、
「メールアドレスも表示」が選ばれた）。

## 実装方針（未着手・次回の実装者向けメモ）

### バックエンド
1. `backend/app/services/google_auth.py`
   - `SCOPES` に `openid` と `https://www.googleapis.com/auth/userinfo.email`
     （または `email`）を追加。
   - `google.oauth2.id_token.verify_oauth2_token`（`google.oauth2.id_token` モジュールは
     `.venv/Lib/site-packages/google/oauth2/id_token.py` に存在確認済み）を使い、
     `exchange_code_for_token()` 実行時（トークン交換時）に一度だけ ID トークンを検証・デコードして
     `email` クレームを取り出す。
   - **毎回のステータス確認（`/api/auth/status`）時に毎回ネットワーク検証を行うのは避ける**
     （ポーリング頻度が高いため）。トークン交換時に取得した email を
     `oauth_token.json` とは別ファイル（例: `oauth_email.json`）、または
     `oauth_token.json` のスキーマを壊さない形で永続化し、`/api/auth/status` はディスク読み込みのみで返す。
     - 注意: `oauth_token.json` は `Credentials.from_authorized_user_info()` で読み込まれるため、
       余計なトップレベルキー（`email` 等）を追加すると読み込みに影響しないか要確認。安全策としては
       別ファイルに分離するのが無難。
   - `is_authenticated()` に加えて `get_authenticated_email() -> str | None` のような関数を追加。
2. `backend/app/api/auth.py`
   - `auth_status()` のレスポンスを `{"authenticated": bool, "email": str | None}` 形式に変更
     （現行の `{"status": "authorized"/"unauthorized"}` は `backend/tests/test_google_auth.py:204-213`
     の既存テストが依存しているため、変更時はテストも合わせて更新する）。

### フロントエンド
1. `frontend/src/api/types.ts` の `AuthStatus` 型は現状の
   `{ authenticated: boolean; email?: string }` のままでよい（バックエンドを型に合わせる）。
2. ログイン状態表示ロジックを `HomePage.tsx` から `AppShell.tsx` へ移設し、
   全ページ共通で `useQuery(['auth-status'], authApi.status)` を呼び出して
   ヘッダーに表示する（他7画面は現状 `headerRight` を渡していないため、
   `AppShell` 内部で自前表示するか、各ページの呼び出し箇所を触らずに済む設計にする）。
3. `HomePage.tsx` から重複する認証バッジ表示コードを削除。
4. `frontend/tests/HomePage.test.tsx` の関連テスト（91-100行目付近）を
   新しい表示場所（`AppShell` 側）に合わせて更新、または `AppShell` 用の新規テストを追加。

### 未確定事項（次回実装者が判断すること）
- 全画面共通化を `AppShell` 内で `useQuery` を直接呼ぶ形にするか、各ページから
  `headerRight` として渡す形を維持するか（後者だと8ページ全てに認証状態取得コードを
  複製することになるため、前者＝`AppShell` 内部で完結させる方が望ましいと考えられる）。
- 再同意（既存トークンでは `email` scope が無いため再ログインが必要）のユーザー向け
  案内文言をどうするか（例: 「メールアドレス表示のため再ログインが必要です」バナー等）。

## 参考ファイル一覧
- `frontend/src/components/ui/AppShell.tsx`
- `frontend/src/pages/HomePage.tsx`
- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/tests/HomePage.test.tsx`
- `backend/app/api/auth.py`
- `backend/app/services/google_auth.py`
- `backend/tests/test_google_auth.py`
