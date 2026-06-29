# Phase 4.2 引き継ぎメモ

## サマリ

ホーム画面・新規プロジェクト作成画面・グローバルルール設定画面の3コンポーネントを実装した。

TDD（RED → test commit → 実装 → GREEN → feat commit）の順序を厳守した。

実装した内容：
1. `frontend/src/pages/HomePage.tsx`：プロジェクト一覧 + 新規作成 + ルール設定 + 認証状態表示
2. `frontend/src/pages/ProjectNewPage.tsx`：新規プロジェクト作成フォーム
3. `frontend/src/pages/GlobalRulesPage.tsx`：グローバルルール設定フォーム
4. テストファイル3件（合計13テスト、全PASS）

---

## 採用方式の決定事項

### UI ライブラリ

Tailwind CSS v4 は className ユーティリティより先に基本レイアウトを確立するため、
Phase 4.2 ではインラインスタイルを多用する簡易実装を採用した。
Phase 4.3 以降で Tailwind クラスへ移行することを推奨する。

### フォームライブラリ

React Hook Form 等の外部フォームライブラリは導入せず、`useState` による素のフォーム管理を採用した。
Phase 4.2 のスコープでは十分であり、後続フェーズで必要なら追加する。

### API モックのパターン

テストでは `vi.mock('../src/api', () => ({ ... }))` + `vi.mocked()` のパターンを確立した。
後続フェーズのテストでも同一パターンが使える。

### @testing-library/dom のインストール

Phase 4.1 では `@testing-library/dom` が node_modules に存在しなかった（peer dep 未解決）。
Phase 4.2 で `npm install -D @testing-library/dom --legacy-peer-deps` を実行して解消した。
（`@testing-library/react` の peer dep。以降は自動解決される）

### ProjectNewPage のフォーム設計

| フィールド | UI | 備考 |
|---|---|---|
| display_name | text input | 必須バリデーション |
| slot_minutes | number input | 既定20分、5〜120の範囲 |
| candidate_dates | textarea | 1行1日（YYYY-MM-DD形式） |
| candidate_time_slots | time input × 2 | 開始/終了の1ペアのみ（追加は Phase 4.3 で検討）|
| student_numbers | textarea | カンマ区切りまたは1行1番号 |

Phase 4.3 でプロジェクト編集画面（ProjectPage.tsx）を実装する際は、
同様のフォーム設計を踏襲すること。

---

## 最終コミットハッシュ

```
c8f62e251874882552b197c3b085186ca6bf0b2f
```

タグ `phase4.2-done` がこのコミット（またはこの handoff コミット）を指す。

---

## 主要な実装上のパラメータ・決定

| 項目 | 値 | 備考 |
|---|---|---|
| vitest テスト総数（フロント） | 13件（全PASS） | smoke 1 + phase4.2 12 |
| バックエンドテスト総数 | 変化なし（Phase 3.4 の 122 件） | |
| renderWithProviders ヘルパー | QueryClientProvider + MemoryRouter | retry: false |
| QueryClient デフォルト設定（テスト用）| `retry: false` | ネットワーク失敗時のリトライ無効化 |
| ナビゲーション方式 | `useNavigate()` | React Router v7 |

---

## 主要ファイル

### 変更（骨格→実装）

- `frontend/src/pages/HomePage.tsx`：プロジェクト一覧、認証状態、ナビゲーションボタン
- `frontend/src/pages/ProjectNewPage.tsx`：新規作成フォーム、バリデーション、mutation
- `frontend/src/pages/GlobalRulesPage.tsx`：グローバルルール読み込み・編集・保存

### 新規

- `frontend/tests/HomePage.test.tsx`：5テスト
- `frontend/tests/ProjectNewPage.test.tsx`：4テスト
- `frontend/tests/GlobalRulesPage.test.tsx`：3テスト

### package.json / package-lock.json の変更

- `@testing-library/dom@^8.x` を devDependencies に追加（`--legacy-peer-deps` で解決）

---

## コミット履歴

```
c8f62e2 feat(phase4.2): implement HomePage/ProjectNewPage/GlobalRulesPage (GREEN)
16abaac test(phase4.2): add HomePage/ProjectNewPage/GlobalRulesPage test cases (RED)
```

RED コミット時点では 12 テストが失敗（スタブコンポーネントに必要な UI 要素なし）。

---

## 後続サブステップへの引き継ぎ事項

### Phase 4.3（プロジェクト画面とForm連携UI）

- `ProjectPage.tsx` と `ProjectRulesPage.tsx` を実装する
- `useParams()` で `projectId` を取得：`const { projectId } = useParams()`
- API クライアントの呼び出しパターンは Phase 4.2 と同様（`vi.mock('../src/api', ...)` でテスト）
- ルーティングは `App.tsx` に設定済み：
  - `/projects/:projectId` → `ProjectPage`
  - `/projects/:projectId/rules` → `ProjectRulesPage`
- ProjectPage のフォームは ProjectNewPage と同様の設計を踏襲する（display_name, candidate_dates 等）
- ポーリング（60秒間隔）は `useEffect` + `setInterval` で実装する

### Phase 4.4a（日程案表示画面）

- `SchedulePage.tsx` を実装する
- ルーティング：`/projects/:projectId/schedule`
- スケジューリング API：`scheduleApi.run(projectId)` → `SchedulingResult`
- `SchedulingResult.assignments` を日付 × 時間枠マトリクスに変換して表示

### Phase 4.4c（保存完了画面）

- `SavedPage.tsx` を実装する
- ドラフト保存後に遷移：`/projects/:projectId/saved`

---

## 未解決の課題・要確認事項

- **保留**：候補時間枠（`candidate_time_slots`）の複数ペア入力 UI は ProjectNewPage で1ペアのみ実装。
  Phase 4.3 のプロジェクト編集画面で複数追加 UI を検討すること
- **保留**：GlobalRulesPage での `teacher_unavailable` リスト編集 UI は未実装（フィールドは API / model に存在する）。
  後続フェーズで追加する場合は、日付・開始時間・終了時間の動的追加 UI が必要
- **保留**：ナビゲーション後に `useQuery` の cache を無効化する必要があるか検討。現状は `staleTime: 30_000`
  のため、プロジェクト作成後に一覧画面へ戻ると最大30秒間古いデータが表示される可能性がある。
  `queryClient.invalidateQueries({ queryKey: ['projects'] })` を mutation の `onSuccess` で呼ぶと解消できる
- **要確認**：ProjectNewPage の出席番号入力が空の場合、`student_numbers: []` で API を呼ぶ。
  バックエンドが空リストを受け付けるか確認する（Phase 2.1 の `ProjectCreateRequest` では `student_numbers: number[]` なので問題ないはず）
