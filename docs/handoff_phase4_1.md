# Phase 4.1 引き継ぎメモ

## サマリ

React + TypeScript のフロントエンドプロジェクトを立ち上げ、API クライアントを整備した。

具体的には以下を実施：

1. **Vite 8 + React 19 + TypeScript 6** で `frontend/` を初期化
2. **追加依存**：`react-router-dom`、`zustand`、`@tanstack/react-query`、`tailwindcss`（v4）、`openapi-typescript`
3. **vitest セットアップ（必須）**：jsdom 環境、`@testing-library/react`、セットアップファイル、smoke test 1 件 PASS
4. **型付き API クライアント**：`frontend/src/api/` に全エンドポイントのラッパーを実装
5. **ルーティング骨格**：全 7 画面の空コンポーネントと React Router ルーティングを配置
6. **FastAPI 静的ファイル配信**：`backend/app/main.py` に `frontend/dist` 存在時の配信ロジックを追加
7. **`scripts/start-dev.ps1` の拡張**（Phase 1.1 からの意図的変更）：`-Mode` パラメータ（All/Backend/Frontend）を追加
8. **`scripts/start.ps1` を新規作成**：`npm run build` → `uvicorn` の本番モード起動

---

## 採用方式の決定事項

### パッケージバージョン

| パッケージ | バージョン | 備考 |
|---|---|---|
| Vite | 8.1.x | scaffold で自動選択 |
| React | 19.2.x | scaffold で自動選択 |
| TypeScript | 6.0.x | scaffold で自動選択 |
| react-router-dom | 7.18.x | |
| zustand | 5.0.x | |
| @tanstack/react-query | 5.101.x | |
| tailwindcss | 4.3.x | @tailwindcss/vite プラグイン経由 |
| vitest | 4.1.x | |
| jsdom | 29.x | |

### Tailwind CSS v4 の使い方

Tailwind CSS v4 は `@tailwindcss/vite` プラグインを使う。`index.css` の先頭に `@import "tailwindcss"` を追加。

### openapi-typescript

Phase 4.1 では手動型定義（`frontend/src/api/types.ts`）を採用。
FastAPI の `/openapi.json` から `openapi-typescript` で自動生成する方式は Phase 4.2 以降での適用を検討。
（現状：バックエンドの `requirements.md §3.2` / `§6` を元に手動で型定義した）

### FastAPI 静的ファイル配信

`frontend/dist` が存在する場合のみ有効化する条件分岐を採用。
開発中は `frontend/dist` が無いため、バックエンドに影響しない。
SPA フォールバック（`/{full_path:path}` → `index.html`）を `/api/*` より後に配置する必要があるため、ルータ登録後に条件付きで `mount` している。

### `start-dev.ps1` の `-Mode All` の起動方式

`All` モードでは、バックエンドを `Start-Process powershell` で別ウィンドウに起動し、フロントエンドを現在のウィンドウで起動する方式を採用。
`-File $thisScript -Mode Backend` を引数として渡すことで、バックエンドウィンドウでも依存インストールチェックが走る。

---

## 最終コミットハッシュ

```
d7d9d91153cddf63a436e0c82d08b0e986a3d9b3
```

タグ `phase4.1-done` がこのコミット（またはこの handoff コミット）を指す。

---

## 主要な実装上のパラメータ・決定

| 項目 | 値 | 備考 |
|---|---|---|
| Vite dev server ポート | 5173 | Vite 既定 |
| バックエンドポート | 8000 | `MEETING_SCHEDULER_PORT` で上書き可 |
| vitest 環境 | jsdom | ブラウザ API エミュレート |
| setupFiles | `./tests/setup.ts` | `@testing-library/jest-dom` を自動追加 |
| テスト総数（フロント） | 1（smoke test） | Phase 4.2 以降で増加 |
| テスト総数（バックエンド） | 122 件（全 PASS） | Phase 3.4 から変化なし |
| API クライアント方式 | 手動型定義 | `frontend/src/api/types.ts` / `client.ts` / `index.ts` |
| ルーティング | React Router v7 | `BrowserRouter` + `Routes` + `Route` |

---

## 主要ファイル

### 新規

- `frontend/` 全体（Vite scaffold + 追加ファイル）
- `frontend/src/api/types.ts`：TypeScript 型定義（backend モデル対応）
- `frontend/src/api/client.ts`：型付き API クライアント
- `frontend/src/api/index.ts`：再エクスポート
- `frontend/src/pages/HomePage.tsx`：ホーム画面（骨格）
- `frontend/src/pages/ProjectNewPage.tsx`：新規プロジェクト作成（骨格）
- `frontend/src/pages/ProjectPage.tsx`：プロジェクト詳細（骨格）
- `frontend/src/pages/ProjectRulesPage.tsx`：プロジェクトルール設定（骨格）
- `frontend/src/pages/GlobalRulesPage.tsx`：グローバルルール設定（骨格）
- `frontend/src/pages/SchedulePage.tsx`：日程案表示（骨格）
- `frontend/src/pages/SavedPage.tsx`：保存完了（骨格）
- `frontend/tests/setup.ts`：vitest セットアップ
- `frontend/tests/smoke.test.ts`：smoke test
- `scripts/start.ps1`：本番モード起動（新規）

### 変更

- `backend/app/main.py`：`frontend/dist` 存在時の静的ファイル配信ロジックを追加（+ `FileResponse` / `StaticFiles` import）
- `scripts/start-dev.ps1`：`-Mode` パラメータ追加（All/Backend/Frontend）、フロント起動ロジック追加

---

## 後続サブステップへの引き継ぎ事項

### Phase 4.2（ホーム画面とプロジェクト一覧）

- **コンポーネントファイルは既に骨格が存在する**：`HomePage.tsx`、`ProjectNewPage.tsx`、`GlobalRulesPage.tsx` を実装に書き換える
- API クライアントは `import { projectsApi, rulesApi, authApi } from '../api'` で呼び出せる
- React Query の `QueryClient` はすでに `App.tsx` に設定済み。`useQuery` / `useMutation` を使える
- ルートパス：`/` → `HomePage`、`/projects/new` → `ProjectNewPage`、`/global-rules` → `GlobalRulesPage`
- **テスト配置先**：`frontend/tests/` 配下に `HomePage.test.tsx` 等を追加する

### Phase 4.3 以降

- 全ページコンポーネントの骨格は `frontend/src/pages/` に配置済み
- `useParams()` で `:projectId` を取得可能（React Router v7）

### Phase 5.2（PDF 出力 UI）

- `SavedPage.tsx` の骨格のみ。`handleDownloadPdf` スタブは Phase 4.4c で追加予定

### openapi-typescript での型自動生成（将来検討）

```powershell
# 開発サーバ起動後：
npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/api/schema.d.ts
```

現状は手動型定義で動いているため急ぎではないが、バックエンドモデルが変わった場合は手動型定義も更新が必要。

---

## 未解決の課題・要確認事項

- **要確認**：Vite 8 / React 19 の組み合わせが最新の beta/RC でなく stable かどうか確認が必要。`npm create vite@latest` で scaffold されたバージョンをそのまま採用している
- **保留**：`--legacy-peer-deps` が tailwindcss インストール時に必要だった。vite 8 と tailwindcss 4 の peer deps の競合。将来のバージョンアップで解消する可能性あり
- **保留**：`frontend/.gitignore` は Vite scaffold の既定値。`frontend/dist/` はルート `.gitignore` でも除外済みなので重複があるが問題なし
- **保留**：`App.css` は scaffold 既定のスタイルが残っている。Phase 4.2 で画面実装する際に整理する
- **未確定**：SPA フォールバックルート（`/{full_path:path}`）は `frontend/dist` が存在しない開発時には登録されない。開発中は Vite dev server（ポート 5173）を使う

---

## vitest セットアップの詳細

```typescript
// vite.config.ts の test 設定
test: {
  environment: 'jsdom',
  setupFiles: ['./tests/setup.ts'],
  globals: true,
}
```

`globals: true` により `describe` / `it` / `expect` をインポートなしで使える。

```typescript
// tests/setup.ts
import '@testing-library/jest-dom'
```

`@testing-library/jest-dom` のカスタムマッチャ（`toBeInTheDocument` 等）が vitest で使える。
