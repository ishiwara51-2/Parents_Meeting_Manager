# Phase 4.3 引き継ぎメモ

## サマリ

プロジェクト詳細画面（`ProjectPage.tsx`）とプロジェクトルール設定画面（`ProjectRulesPage.tsx`）を実装した。

TDD（RED → test commit → 実装 → GREEN → feat commit）の順序を厳守した。

実装した内容：
1. `frontend/src/pages/ProjectPage.tsx`：プロジェクト詳細 + Form 連携 + 受領状況 + ポーリング
2. `frontend/src/pages/ProjectRulesPage.tsx`：プロジェクト固有ルール設定フォーム
3. テストファイル 2 件（合計 15 テスト、追加後の全テスト数 28 件、全 PASS）
4. `frontend/src/api/types.ts` の `ResponsesStatus` 型バグ修正（`not_received` → `pending`、`project_id` 追加）

---

## 採用方式の決定事項

### ポーリング方式

自動ポーリングは `useEffect` + `setInterval` を採用（requirements.md §4.4 の「N 秒間隔」）。

```typescript
useEffect(() => {
  if (!projectId) return
  const id = setInterval(() => {
    responsesApi.sync(projectId)
      .then(() => queryClient.invalidateQueries({ queryKey: ['responses-status', projectId] }))
      .catch(() => { /* サイレント */ })
  }, POLLING_INTERVAL_MS)  // 60_000 ms
  return () => clearInterval(id)
}, [projectId, queryClient])
```

- バックグラウンドポーリングのエラーはサイレント（ユーザーには表示しない）
- 手動ボタン（`useMutation` 経由）のエラーは `syncError` state で表示する
- `clearInterval` をクリーンアップ関数で呼ぶことで、コンポーネントアンマウント時に自動停止

### Form 情報の表示ロジック

- Form 未作成時（`formApi.get` が 404 → `isError=true`）：「候補日程聴取用 Google Form 作成」ボタンを表示
- Form 作成済み時（`formApi.get` が 200 → `formInfo` あり）：`responderUri` とコピーボタンを表示
- Form 作成直後（`createFormMutation.data` あり）：`formInfo ?? createFormMutation.data` で即座に表示
- `retry: false` を指定して 404 エラーを即時確定させ、ローディング待ちを最小化

### ResponsesStatus 型修正（バグ修正）

Phase 4.1 で定義した型が誤っていた（`not_received` vs バックエンドが返す `pending`）。

| 変更前 | 変更後 |
|---|---|
| `not_received: number[]` | `pending: number[]` |
| `project_id` フィールドなし | `project_id: string` 追加 |

`client.ts` の `responsesApi.status` の戻り値型 `ResponsesStatus` も自動的に修正される。

### ProjectRulesPage のスコープ

Phase 4.3 では `global_constraints`（max_consecutive_slots / forced_break_slots / max_slots_per_day）のみ実装。
`student_constraints`（ペアリング / 時間帯回避 / 優先 / 所要時間倍率）の UI は Phase 4.4 以降での追加を想定。

---

## 最終コミットハッシュ

```
cc5c4f671e82e04b08e287213eceacf1a322e677
```

タグ `phase4.3-done` がこのコミット（または handoff コミット）を指す。

---

## 主要な実装上のパラメータ・決定

| 項目 | 値 | 備考 |
|---|---|---|
| ポーリング間隔 | `60_000` ms（60 秒） | `POLLING_INTERVAL_MS` 定数 |
| Form 情報 retry | `false` | 404 を即座に `isError=true` にするため |
| プロジェクト画面ルート | `/projects/:projectId` | `useParams()` で `projectId` を取得 |
| ルール設定ルート | `/projects/:projectId/rules` | 同上 |
| vitest テスト総数（フロント） | 28 件（全 PASS） | smoke 1 + phase4.2 13 + phase4.3 14 |
| バックエンドテスト総数 | 変化なし（Phase 3.4 の結果を継承） | |

---

## 主要ファイル

### 変更（骨格→実装）

- `frontend/src/pages/ProjectPage.tsx`：全機能実装（約 200 行）
- `frontend/src/pages/ProjectRulesPage.tsx`：ルール設定フォーム（約 130 行）

### 新規

- `frontend/tests/ProjectPage.test.tsx`：12 テスト
- `frontend/tests/ProjectRulesPage.test.tsx`：3 テスト

### 修正（バグ修正）

- `frontend/src/api/types.ts`：`ResponsesStatus` 型を修正（`pending` + `project_id`）

---

## コミット履歴

```
cc5c4f6 feat(phase4.3): implement ProjectPage and ProjectRulesPage (GREEN)
1256aed test(phase4.3): add ProjectPage/ProjectRulesPage test cases (RED)
```

RED コミット時点では 15 件が全 FAIL（スタブ実装に必要な UI 要素が存在しないため）。

---

## 後続サブステップへの引き継ぎ事項

### Phase 4.4a（日程案表示画面）

- `SchedulePage.tsx` を実装する（骨格は `frontend/src/pages/SchedulePage.tsx` に配置済み）
- ルーティング：`/projects/:projectId/schedule` → `SchedulePage`
- `ProjectPage.tsx` の「面談日程案作成」ボタンがこのルートへ遷移する
- スケジューリング API：`scheduleApi.run(projectId)` → `SchedulingResult`
- `SchedulingResult.assignments` を日付 × 時間枠マトリクスに変換して表示
- 解なし時は `violated_constraints` / `unassigned_students` を画面上部に表示
- テストパターンは Phase 4.3 と同様（`renderWithProviders` + `Routes` + `useParams`）

### Phase 4.4b（DnD と警告）

- `dnd-kit` のインストール：`npm install @dnd-kit/core @dnd-kit/sortable --legacy-peer-deps`
- `SchedulePage.tsx` を拡張（Phase 4.4 シリーズは意図的な段階拡張として例外許可）

### Phase 4.4c（保存完了画面）

- `SavedPage.tsx` を実装する
- ルーティング：`/projects/:projectId/saved`
- ドラフト保存 API：`draftsApi.save(projectId, req)` → `Draft`
- ドラフトロック解除 API：`draftsApi.unlock(projectId)` → `Draft`

---

## 未解決の課題・要確認事項

- **保留**：`ProjectRulesPage.tsx` の `student_constraints`（ペアリング / 時間帯回避 / 優先 / 所要時間倍率）の UI が未実装。Phase 4.4c 以降で追加する場合は動的な行追加 UI が必要
- **保留**：`ProjectPage.tsx` でのプロジェクトメタ情報編集（`ProjectUpdateRequest` を使った PUT 保存）は未実装。現在は読み取り専用表示のみ。Phase 4.4 以降で必要なら `editMode` state で表示切り替えを追加する
- **保留**：URL コピーボタンは `navigator.clipboard.writeText` を使用。HTTP（非 HTTPS）環境では動作しない可能性がある（ローカル開発の `localhost` は例外的に許可されるため通常問題なし）
- **要確認**：自動ポーリングで Form 未作成の場合、`responsesApi.sync` が 404 を返す（`form.json がありません` という detail）。この際の `catch(() => {})` がサイレントでよいか UI 要件を確認する。現状はサイレント失敗
- **保留**：`setInterval` の `projectId` 依存：`projectId` が変わる（別プロジェクトへ SPA 遷移）場合、`useEffect` のクリーンアップで古いインターバルが停止し、新しいインターバルが開始される。正常動作するが、同一コンポーネントが再利用されるケースは考慮済み
