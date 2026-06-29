# Phase 3.3a 引き継ぎメモ

## サマリ

Phase 3.2 で実装した `app.services.scheduler.solve_hard` に **ソフト制約 5 種**を
追加し、目的関数を **「W_PLACE × 配置数 − ソフトペナルティ総和」（辞書式優先）** に
拡張した。Phase 3.2 の `solve_hard` は新しい統合関数 `solve` のエイリアスとして
互換維持されており、既存の 14 件のハード制約テストは引き続き全 PASS である。

新規ソフト制約テストは 16 件（最低限 8 件 + 防御テスト 8 件）。全 PASS。

テスト総数：**既存 80 + 新規 16 = 96 件、全 PASS（約 4 秒）**。

## 採用方式・決定事項

### 1. ソフト制約の定式化（5 種類）

| ソフト制約 | 定式 | 重み源 |
|---|---|---|
| 5. 連続コマ数上限・強制空きコマ | 同一日内の連続 `window_size = M + max(1, B)` スロットで占有合計が `M` を超えた分を `excess` 変数で表現、`weight × excess` をペナルティ化 | `DEFAULT_GLOBAL_SOFT_WEIGHT = 5`（モジュール定数） |
| 6. 1 日あたりコマ数上限 | 各日の占有合計が `D` を超えた分を `excess` 変数で表現、`weight × excess` | `DEFAULT_GLOBAL_SOFT_WEIGHT = 5` |
| 7. ペアリング | 全ペア (a, b) について `\|start_pos[a] - start_pos[b]\|` を big-M 線形化で「両者配置時のみ」加算 | `PairingConstraint.weight` |
| 8. 時間帯回避 | `avoid_after`/`avoid_before` 範囲内のスロットでの x[(i,s)] にペナルティ | `AvoidTimeConstraint.weight` |
| 9. 時間帯優先 | `prefer_after`/`prefer_before` の **外側**のスロットでの x[(i,s)] にペナルティ（「優先帯にボーナス」ではなく「優先帯外にペナルティ」） | `PreferTimeConstraint.weight` |

連続コマ制約のウィンドウ生成は、同一日かつ「物理的に隣接（end == 次の start）」な
範囲に限定する。これにより 18:00-18:20 と 19:00-19:20 のような時間的空白を挟む配置を
「連続コマ」と誤検出しない。

### 2. 目的関数：**辞書式優先**（重み付き総和ではない）

```
maximize  W_PLACE × Σ x[i, s]  −  Σ soft_penalty_terms
```

- `W_PLACE = _compute_w_place(rules, n_slots, n_students)` で動的に計算
- 「ソフト制約ペナルティの理論最大値 + n_students + 1」以上を保証
- これにより 1 名でも多く配置することが、どんなソフトペナルティ削減よりも優先される

**「重み付き総和」を採用しなかった理由**：
- requirements.md §4.6.4「ハード制約で解なしの場合は緩和しない」の精神と一致させる
- 「重みが大きいソフト制約のために配置を諦める」という挙動は要件と矛盾する
- Phase 3.2 引き継ぎ（5d4dfb5）で示唆された方式と一致

### 3. グローバルソフト制約の重み正規化

`Rules.GlobalConstraints` は連続コマ・1 日上限に **明示的な weight フィールドを持たない**
（Phase 1.2 で確定）。Phase 3.3a では以下のように扱う：

- モジュール定数 `DEFAULT_GLOBAL_SOFT_WEIGHT = 5` を採用
- 値 5 は per-student ソフトの重み範囲（0〜10）の中央値
- 各ソフト制約間で極端な優劣が生じない設計意図
- 将来 `GlobalConstraints` モデルに weight フィールドを追加する場合、本定数を
  取り去り、Rules から取り出すよう変更可能

**重み正規化の判断記録**：
- 「最大重み 10 で配置インセンティブとどう比較するか」については、`W_PLACE` を
  動的計算することで対応。具体的には max_soft_penalty 上限の和を取り、その +1 以上を
  保証する。これにより per-student weight の数値範囲（0〜10）と global の重み（5）の
  混在環境でも「配置数 > ソフト制約遵守」の辞書式優先が崩れない。

### 4. ペアリング制約の「両者配置時のみペナルティ」

big-M 線形化:

```
diff_var       ∈ [-n_slots, n_slots]   diff_var = start_pos[a] - start_pos[b]
abs_diff_var   ∈ [0, n_slots]          model.AddAbsEquality(abs_diff_var, diff_var)
both_var       ∈ {0, 1}                both = placed[a] AND placed[b]
effective_var  ∈ [0, n_slots]
                    effective_var ≤ big_m × both_var          ← both=0 → effective=0 強制
                    effective_var ≤ abs_diff_var              ← 距離の上限
                    effective_var ≥ abs_diff_var − big_m × (1 − both_var)
penalty += weight × effective_var
```

これにより、片方未配置 / 両方未配置のときペナルティが暴発しない。

### 5. 時間帯優先の実装方針：**「優先帯外にペナルティ」**

「優先帯にボーナス（負ペナルティ）」ではなく「優先帯外にペナルティ」と実装した理由:

- ボーナス方式：未配置（x=0）でもボーナスゼロ → 配置インセンティブを歪めない
- ボーナス方式：配置数最大化との相互作用で不自然な解が出る可能性
- ペナルティ方式：未配置（x=0）はペナルティゼロで自然、配置時のみ「優先帯外なら課金」

### 6. 重複 Response の扱い（Phase 3.2 から継承）

同一 `student_number` が `responses` に複数あった場合、最初に出現したものを採用し、
警告ログを出す（Phase 2.3 の `list_latest_per_student` が既に最新版のみ返す前提だが、
防御的に重複排除する）。

### 7. 公開 API の互換維持

- `solve(project, responses, rules)`: Phase 3.3a の新公開関数
- `solve_hard = solve`: モジュールトップで定義したエイリアス
- Phase 3.2 で書かれた呼び出し（`from app.services.scheduler import solve_hard`）は
  そのまま動作する
- ソフト制約が全く無い（または weight=0）の場合、`solve` はハード制約のみと同じ
  結果を返すため、Phase 3.2 の挙動は完全に保たれる
- 既存 `test_scheduler_hard.py` の 14 件は全 PASS のまま

## 主要な実装上のパラメータ・決定

| 項目 | 値 | 備考 |
|---|---|---|
| `DEFAULT_SOLVER_TIME_LIMIT_SECONDS` | 60.0 秒 | Phase 3.2 から無変更 |
| `DEFAULT_GLOBAL_SOFT_WEIGHT` | 5 | グローバルソフト制約（連続コマ・1日上限）の暗黙重み |
| `W_PLACE` 計算式 | `max_soft_penalty + n_students + 1` 以上 | `_compute_w_place(rules, n_slots, n_students)` で動的計算 |
| 連続コマウィンドウサイズ | `M + max(1, B)` | M=max_consecutive_slots, B=forced_break_slots。B=0 でも window=M+1 |
| 連続コマウィンドウ採用条件 | 同一日 + 物理連続（end == next.start） | 時間空白を跨ぐ範囲は除外 |
| ペアリング距離計算 | 位置インデックス差の絶対値 | 同日内は時刻順、別日は日付順。big-M 線形化で「両者配置時のみ」 |
| big-M（ペアリング） | `n_slots`（または 1） | ペアリングの線形化に使用 |
| 時間帯回避の判定 | `slot.start >= avoid_after` / `slot.start < avoid_before`（半開区間） | 端点共有時の挙動を明確化 |
| 時間帯優先の判定 | `slot.start >= prefer_before` / `slot.start < prefer_after`（**外側**にペナルティ） | 「優先帯外」を avoid 風に表現 |
| `solve_hard` の正体 | `solve_hard = solve` のエイリアス | モジュールトップで `solve` 定義後に代入 |
| テスト総数 | 既存 80 + 新規 16 = **96 件** | 全 PASS（約 4 秒） |

## 主要ファイル

### 新規

- **`backend/tests/test_scheduler_soft.py`**（16 件、Phase 3.3a 中核テスト）
  - 時間帯回避（avoid_after / avoid_before）
  - 時間帯優先（prefer_before / prefer_after）
  - ペアリング（隣接配置）
  - 連続コマ数上限 / 強制空きコマ
  - 1 日あたりコマ数上限
  - weight=0 の挙動（pairing / avoid / prefer すべて）
  - 重みの大小（高重みが支配）
  - ハード / ソフト混在
  - 配置数最大化の優先（辞書式優先）
  - ソフト制約 0 件時のハード互換
  - `solve_hard` エイリアス検証

### 変更

- **`backend/app/services/scheduler.py`**
  - モジュール docstring を全面更新（ハード + ソフト制約の網羅説明）
  - import に `AvoidTimeConstraint`, `PairingConstraint`, `PreferTimeConstraint` を追加
  - `DEFAULT_GLOBAL_SOFT_WEIGHT = 5` 定数を追加
  - 内部ヘルパ追加:
    - `_build_occupancy_expr`: 各スロットの占有式を返す
    - `_add_consecutive_slot_penalty`: 連続コマ数ペナルティ項
    - `_add_daily_slot_penalty`: 1 日上限ペナルティ項
    - `_add_pairing_penalty`: ペアリングペナルティ項（big-M 線形化）
    - `_add_avoid_time_penalty`: 時間帯回避ペナルティ項
    - `_add_prefer_time_penalty`: 時間帯優先ペナルティ項
    - `_compute_w_place`: 辞書式優先の大重み計算
  - 公開 API:
    - `solve(...)`：Phase 3.3a の新統合関数
    - `solve_hard = solve`：Phase 3.2 互換エイリアス
  - 旧 `solve_hard` の関数定義は除去（エイリアスに統合）

### Phase 1.x / 2.x / 3.1 / 3.2 からの無変更

- `backend/app/models/*`（モデル変更なし）
- `backend/app/repositories/*`
- `backend/app/services/google_auth.py`, `google_forms.py`, `polling.py`
- `backend/app/api/*`
- `backend/app/main.py`, `dependencies.py`, `config.py`
- `backend/tests/conftest.py`, 既存テストファイル
- `backend/tests/test_scheduler_hard.py`（14 件全 PASS のまま無変更）
- `scripts/*.ps1`, `.gitignore`, `.gitattributes`, `pyproject.toml`

## コミット履歴

```
55af334 feat(phase3.3a): implement scheduler soft constraints with lexicographic priority (GREEN)
28a2ccf test(phase3.3a): add scheduler soft constraints test cases (RED)
```

### 最終コミットハッシュ

```
55af33479260e96b0abaf41f311ac62df6356bc3  feat(phase3.3a): implement scheduler soft constraints with lexicographic priority (GREEN)
```

### TDD 厳格検証

RED コミット時点で `tests/test_scheduler_soft.py` は
`ImportError: cannot import name 'solve' from 'app.services.scheduler'` で
collection error となり 16 件全てが失敗扱い（pytest exit code != 0）であることを
実機確認した上で test commit を打ち、その後実装で全 PASS（96/96）に持ち込んだ。

`Check-PhaseDone.ps1` の TDD 厳格検証は
`git checkout 28a2ccf && pytest tests/test_scheduler_soft.py` で実機検証可能。

## 後続サブステップへの引き継ぎ事項

### Phase 3.3b（スケジューラ API 統合とパフォーマンステスト）

- API ハンドラ `POST /api/projects/{id}/schedule` の呼び出し例:

  ```python
  from app.services.scheduler import solve  # solve_hard でも可（エイリアス）

  project = project_repo.get(project_id)
  responses = response_repo.list_latest_per_student(project_id)
  rules = rule_repo.get_project_rules(project_id)
  result = solve(project, responses, rules)
  return result.model_dump()
  ```

- **パフォーマンス目標**: 30 名・5 日 × 10 コマで 10 秒以内
  - ソフト制約追加で CP-SAT の探索空間が広がるため、`DEFAULT_SOLVER_TIME_LIMIT_SECONDS=60` の
    範囲で実測する必要あり
  - 必要なら `solver.parameters.num_search_workers = N`（CPU コア数）や
    `cp_model.CpSolver().parameters.search_branching = cp_model.PORTFOLIO_SEARCH` を試す
  - 並列度の上げ過ぎは Windows プロセス起動のオーバーヘッドで逆効果になり得るので、
    実測で決める
- `time_limit_seconds` を API ハンドラ経由で上書き可能にすると、フロントエンドから
  「軽い再試行 vs じっくり最適化」を切り替えられる

### Phase 3.4（ドラフト保存）

- `SchedulingResult` のフィールド名は Draft モデル（`app.models.draft.Draft`）と一致
  （`assignments`, `unassigned_students`, `violated_constraints`）
- ただし `violated_constraints` は `list[str]`（Phase 3.2 から継続）、Draft は
  `list[dict[str, Any]]` → Phase 3.4 で変換またはモデル統一が必要

### Phase 4.4a（日程案表示）

- マトリクス表示の入力は `SchedulingResult`。`violated_constraints` の文字列リストを
  画面上部に表示
- ソフト制約違反については Phase 3.3a の段階では文字列メッセージとして詳細化されておらず、
  「未配置生徒」と「候補ゼロ / 衝突」の区分のみ表示される（Phase 3.2 と同じ）

### Phase 4.3（プロジェクトルール画面）

- per-student ソフト制約（pairing / avoid_time / prefer_time）の重み 0〜10 を UI で
  設定する。`weight=0` は「該当制約を無効化」と等価であることを UI ヒントに含めると親切

## 未解決の課題・要確認事項

- **保留**：`GlobalConstraints` に `weight` フィールドを追加するかどうか
  （現状は scheduler 側で `DEFAULT_GLOBAL_SOFT_WEIGHT = 5` 固定）。
  ユーザーが「連続コマと時間帯回避でどちらを優先するか」を細かく調整したい
  ユースケースが出てきたら、モデル拡張を検討する
- **保留**：`AvoidTimeConstraint` / `PreferTimeConstraint` で `avoid_after`/`avoid_before`
  の両方が `None` または両方が指定されたケースのバリデーションが未実装
  （Phase 1.2 引き継ぎからの継続）。今回の実装は「両方 None なら何もペナルティしない」
  「両方指定なら両方の条件を加算」として防御的に動く。将来 UI で「片方のみ指定」
  バリデーションを入れる場合に再検討
- **要確認**：ペアリング制約で対象生徒が 3 人以上のとき、全ペア組み合わせで距離を加算
  している（つまり 3 人の場合は 3 ペア = C(3,2) のペナルティ）。これが「3 人を
  クラスタリングする」挙動として要件に合っているかは要確認。代替案は「最小スパニング
  ツリー的距離合計」「最大距離のみ」など
- **保留**：CP-SAT のソルバ並列度（`num_search_workers`）はデフォルト。Phase 3.3b の
  パフォーマンス測定で必要に応じてチューニング
- **保留**：`W_PLACE` は理論上限を取っているため、大きな問題では大きな係数になる
  （例: 30 名 × 50 スロット で W_PLACE が数千〜数万）。CP-SAT は int64 で扱えるので
  問題ないが、ソルバ内部の数値スケールが大きくなり、探索ヒューリスティクスに影響する
  可能性は要監視
- **要確認**：ソフト制約「ペアリング」で `student_numbers` に未受領生徒が含まれる場合、
  `student_index_map` のフィルタで自動的に除外される。これが要件として正しい挙動か
  （ペアの片方が未受領なら制約自体を無効化するのが妥当）

## 動作確認手順（参考）

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_scheduler_soft.py tests/test_scheduler_hard.py -v
```

期待される出力:
```
30 passed in ~1 sec
```

ソフト制約挙動の REPL 確認例:

```powershell
cd backend
.\.venv\Scripts\python.exe -c "
from datetime import date, datetime, time, timezone
from app.models import (Project, TimeSlot, Response, Availability, Rules,
                       GlobalConstraints, AvoidTimeConstraint)
from app.services.scheduler import solve

project = Project(
    project_id='demo', display_name='デモ',
    created_at=datetime(2026,1,1,tzinfo=timezone.utc), status='in_progress',
    slot_minutes=20,
    candidate_dates=[date(2026,7,15)],
    candidate_time_slots=[TimeSlot(start=time(16,0), end=time(16,20)),
                          TimeSlot(start=time(18,0), end=time(18,20))],
    student_numbers=[1],
)
responses = [
    Response(project_id='demo', student_number=1,
             submitted_at=datetime(2026,6,24,tzinfo=timezone.utc),
             google_form_response_id='r_1',
             availability=[Availability(date=date(2026,7,15), start=time(16,0), end=time(16,20)),
                           Availability(date=date(2026,7,15), start=time(18,0), end=time(18,20))])
]
rules = Rules(
    global_constraints=GlobalConstraints(max_consecutive_slots=10,
                                          forced_break_slots=0, max_slots_per_day=20),
    student_constraints=[
        AvoidTimeConstraint(student_number=1, avoid_after=time(17,0), weight=10)
    ],
)
print(solve(project, responses, rules).model_dump_json(indent=2))
"
```

出力例（avoid_after=17:00 が効いて 16:00 に配置される）:

```json
{
  "assignments": [
    {"student_number": 1, "date": "2026-07-15", "start": "16:00", "end": "16:20"}
  ],
  "unassigned_students": [],
  "violated_constraints": []
}
```

## 作成ファイル一覧

- `backend/tests/test_scheduler_soft.py`（新規・16 件）
- `backend/app/services/scheduler.py`（拡張、Phase 3.2 互換維持）
- `docs/handoff_phase3_3a.md`（本ドキュメント）
