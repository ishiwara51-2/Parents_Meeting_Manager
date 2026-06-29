# Phase 3.2 引き継ぎメモ

## サマリ

OR-Tools CP-SAT モデルでハード制約のみを考慮するスケジューラ
`app.services.scheduler.solve_hard` を純粋関数として実装した。
ハード制約は requirements.md §4.6.2 の 4 種（候補日時範囲内 / 教師不可時間帯除外 /
1 コマ 1 生徒 / 所要時間倍率）。

TDD（RED コミット → 14 件中 collection error で全失敗を確認 → 実装 → GREEN）の順序で進めた。
最終テスト数：**既存 66 + 新規 14 = 80 件、全 PASS**。

## 採用方式・決定事項

### 1. CP-SAT モデル化方針：「開始位置基準」

決定変数 `x[i, s]`:

```
x[i, s] = 1 ⇔ 生徒 i の面談が候補スロット s から「始まる」
              （生徒 i は [s, s + mult_i - 1] のスロットを占有する）
```

| 採用理由 | 補足 |
|---|---|
| 所要時間倍率（multiplier）が自然に表現できる | 「mult スロット連続占有」を「開始位置 1 つ」に集約 |
| スロット競合チェックが単純 | 「スロット t を占有する全変数の和 ≤ 1」で書ける |
| Phase 3.3a 拡張時に再利用できる | 連続コマ数上限・1 日上限は「位置範囲のスライディングウィンドウペナルティ」として同モデルに足せる |
| 探索空間が枝刈り済みで小さい | `_compute_valid_starts` で「ハード制約 1/2/4 を満たす開始位置」のみを CP-SAT に渡すため、変数数は実質 (生徒数 × 平均有効開始数) |

代替案として「(生徒, スロット) ごとに 1 つの bool 変数」を割当占有として持つモデルも検討したが、
所要時間倍率の表現が「複数変数の AND を 1 で束ねる」必要があり可読性・保守性で劣るため不採用。

### 2. 制約の定式化

| 制約 | 定式 | 備考 |
|---|---|---|
| ハード 1（候補範囲内） | `_availability_to_slot_indices` で `availability` を `all_slots` の index 集合にマップ。範囲外申告は黙って捨てる | Form がチェックボックスマトリクスを candidate_time_slots 単位で出すため、(date, start, end) の完全一致で十分 |
| ハード 2（教師不可） | `_slot_blocked_by_teacher_unavailable` で重なるスロットを `valid_starts` 算出時に除外（半開区間 `[start, end)`、端点共有は重ならない扱い） | RFC 5545 / iCal 等と同じ慣例 |
| ハード 3（1 コマ 1 生徒） | 各スロット t に対し `sum_{(i, s) : s ≤ t < s + mult_i} x[(i, s)] ≤ 1` | 1 名以下の場合は trivially satisfied のため枝刈り |
| ハード 4（所要時間倍率） | `_compute_valid_starts` で開始位置 s の検証時に、`slots[s..s+mult-1]` が「同一日付」「隣接（slots[k].end == slots[k+1].start）」「全て申告可」「全て教師可」を要求。配置時は `slots[s].start` 〜 `slots[s+mult-1].end` を占有 | 日跨ぎ・空白挟みは認めない |

加えて「各生徒は最大 1 回」: `sum_s x[(i, s)] ≤ 1`。
これにより `= 0` ⇒ 未配置、`= 1` ⇒ 配置、を表現する。

### 3. 目的関数：配置数の最大化

```
maximize sum(x[i, s])
```

ハード制約のみなので「何も配置しない」が常に実行可能解（trivially satisfied）。
従って CP-SAT は INFEASIBLE を返さず、最大配置を含む FEASIBLE / OPTIMAL を返す。
配置できなかった生徒は `unassigned_students` に列挙する。

Phase 3.3a でソフト制約を載せる際は、目的関数を
**「(配置生徒数 × 大重み) - (ソフト制約ペナルティ総和)」** に拡張する想定。
「大重み」は `max_soft_penalty × (生徒数 + 1)` 程度を設定して、
「配置生徒数を優先、同点ならソフト制約遵守」の辞書式順序を実現する。

### 4. 解なし時の挙動

requirements.md §4.6.4「違反している制約の一覧を表示」「未配置となった生徒の出席番号一覧を表示」
を実装。Phase 3.2 では `violated_constraints: list[str]` で説明文を返す。

未配置生徒の原因区分:
- **候補ゼロ系**（`valid_starts[i]` が空）→「候補日時 / 教師不可時間帯 / 所要時間倍率の制約により開始可能スロットが無い」
- **衝突系**（`valid_starts[i]` が非空だが配置されず）→「他生徒とのスロット競合により配置できない」

両方該当する場合はそれぞれの説明を別の要素として返す。

### 5. 純粋関数性

`solve_hard` は副作用なし：ファイル I/O / DB アクセスを行わず、入力 `project`/`responses`/`rules`
を変更しない（`test_solve_hard_is_pure_function` で `copy.deepcopy` 比較により検証済み）。

### 6. 重複 Response の扱い

同一 `student_number` が `responses` に複数あった場合、最初に出現したものを採用し、
警告ログを出す（`Phase 2.3` の `list_latest_per_student` が既に最新版のみ返す前提だが、
防御的に重複排除する）。

## 主要な実装上のパラメータ・決定

| 項目 | 値 | 備考 |
|---|---|---|
| `DEFAULT_SOLVER_TIME_LIMIT_SECONDS` | 60.0 秒 | `cp_model.CpSolver().parameters.max_time_in_seconds` に設定。`solve_hard(..., time_limit_seconds=...)` で上書き可能 |
| ortools バージョン | `>=9.10`（pyproject.toml）。実機 install は `9.15.6755` | Python 3.14 ホイール（cp314）が提供されていることを確認 |
| protobuf | `6.33.6` に降格（ortools の依存）| 旧 `7.35.1` から自動的に置換。Google API クライアント・auth は問題なく動作（既存 66 テスト全 PASS で確認） |
| numpy | 新規 `2.5.0` 追加（ortools 経由） | テストに副作用なし |
| 半開区間の慣例 | `[start, end)` | 教師不可時間帯と候補スロットの重なり判定。端点共有（slot.end == ta.start）は重ならない扱い |
| 隣接スロット判定 | `slots[k].date == slots[k+1].date AND slots[k].end == slots[k+1].start` | 空白を挟むスロット列は所要時間倍率で連続扱いされない |
| 結果ソート順 | assignments は `(date, start, student_number)` 昇順、unassigned_students は数値昇順 | UI 表示と diff 比較の安定性のため |
| テスト総数 | 既存 66 + 新規 14 = **80 件** | 全 PASS（1.04 秒、CP-SAT のオーバーヘッド込み） |

## 主要ファイル

### 新規

- **`backend/app/services/scheduler.py`**（417 行、Phase 3.2 中核）
  - 公開 API：`solve_hard(project, responses, rules, *, time_limit_seconds=60.0) -> SchedulingResult`
  - 公開モデル：`SchedulingResult(assignments, unassigned_students, violated_constraints)`
  - 公開定数：`DEFAULT_SOLVER_TIME_LIMIT_SECONDS = 60.0`
  - 内部ヘルパ：`_time_to_minutes`, `_slots_overlap`, `_build_all_slots`,
    `_slot_blocked_by_teacher_unavailable`, `_availability_to_slot_indices`,
    `_get_multiplier_map`, `_compute_valid_starts`
- **`backend/tests/test_scheduler_hard.py`**（14 件・実装指示書「最低限 7 件」+ 防御テスト 7 件）

### 変更

- `backend/pyproject.toml`
  - `"ortools>=9.10"` を `dependencies` に追加

### Phase 1.x / 2.x / 3.1 からの無変更

- `backend/app/models/*`（Phase 3.2 でモデル拡張なし。Draft.violated_constraints の構造化は Phase 3.3a 以降に持ち越し）
- `backend/app/repositories/*`
- `backend/app/services/google_auth.py`, `google_forms.py`, `polling.py`
- `backend/app/api/*`
- `backend/app/main.py`, `dependencies.py`, `config.py`
- `backend/tests/conftest.py`, 既存 9 件のテストファイル
- `scripts/*.ps1`, `.gitignore`, `.gitattributes`

## コミット履歴

```
51ed06b feat(phase3.2): implement scheduler hard constraints with CP-SAT (GREEN)
123c0e3 test(phase3.2): add scheduler hard constraints test cases (RED)
```

### 最終コミットハッシュ

```
51ed06b54723d2e285c226f3c1f34500b2c1adcc  feat(phase3.2): implement scheduler hard constraints with CP-SAT (GREEN)
```

### TDD 厳格検証

RED コミット時点で `tests/test_scheduler_hard.py` は
`ModuleNotFoundError: No module named 'app.services.scheduler'` で
collection error となり 14 件全てが失敗扱い（pytest exit code != 0）であることを確認した上で
test commit を打ち、その後実装で全 PASS（14/14）に持ち込んだ。

`Check-PhaseDone.ps1` の TDD 厳格検証は
`git checkout 123c0e3 -- backend/tests/test_scheduler_hard.py && pytest tests/test_scheduler_hard.py`
で実機検証可能。

## 後続サブステップへの引き継ぎ事項

### Phase 3.3a（ソフト制約モデル）

- **ソフト制約は同じ `x[i, s]` モデルにペナルティ変数を足す形で追加できる**:
  - 連続コマ数上限：スライディングウィンドウ `sum_{k=t..t+L} occupies(i, k) > max_consecutive_slots` を
    ペナルティ Bool でリンクし、目的関数に減算
  - 1 日上限：日付ごとの占有数 `sum_{t in day} occupied(t) > max_slots_per_day` を同様
  - ペアリング：兄弟生徒 (a, b) について `|start_a - start_b|` のペナルティ
  - 時間帯回避：`x[i, s]` のうち `slot[s].start >= avoid_after` のものに重みペナルティ
  - 時間帯優先：`x[i, s]` のうち `slot[s].start <= prefer_before` のものに重み「ボーナス」（負ペナルティ）
- **目的関数の拡張**:

  ```python
  W_PLACE = max_soft_penalty_total * (num_students + 1)  # 配置数優先のための大重み
  model.Maximize(W_PLACE * sum(x.values()) - sum(soft_penalties))
  ```

  これで「配置生徒数最大化」が優先される（辞書式順序）。
- **既存ハードテストの維持**:
  - `test_scheduler_hard.py` の 14 件は Phase 3.3a でもそのまま通る必要がある
    （ソフト制約が `weight=0` ならハードのみと同じ挙動になるはず）
- **タイムリミット**:
  - ソフト制約追加で探索空間が広がるため、`DEFAULT_SOLVER_TIME_LIMIT_SECONDS = 60` 秒では
    Phase 3.3b の「30 名・5 日 × 10 コマで 10 秒以内」目標に届くか要検証。
  - 必要なら `solver.parameters.num_search_workers = 8` 等の並列化や、
    `cp_model.CpSolver().parameters.search_branching = cp_model.PORTFOLIO_SEARCH` を試す

### Phase 3.3b（API 統合）

- API ハンドラ `POST /api/projects/{id}/schedule` の入力データ取得:
  ```python
  project = project_repo.get(project_id)
  responses = response_repo.list_latest_per_student(project_id)  # 既受領生徒のみ
  rules = rule_repo.get_project_rules(project_id)
  result = solve_hard(project, responses, rules)
  return SchedulingResult.model_dump()
  ```
- 未受領生徒（`get_pending_student_numbers`）は `solve_hard` には渡さない
  （= スケジューリング対象外、requirements.md §4.6.1）。API レスポンスに別途
  「未受領一覧」を載せるかは Phase 3.3b で決める
- **エラー応答**:
  - プロジェクト不在 → 404
  - 受領 0 件 → `assignments=[], unassigned_students=[], violated_constraints=[]` の正常応答（呼び出し側に判断を委ねる）
  - ソルバタイムアウト時の挙動：CP-SAT は通常 OPTIMAL/FEASIBLE を返すが、`UNKNOWN` を返したら
    `violated_constraints` に「タイムアウト」を追記して部分解を返す（既に scheduler.py で防御済み）
- **パフォーマンステスト**:
  - `backend/tests/test_schedule_perf.py` で `pytest.mark.slow`
  - 30 名 × 5 日 × 10 コマ = 50 候補スロット、ランダム availability で `time.perf_counter()` 計測

### Phase 3.4（ドラフト保存）

- `SchedulingResult` のフィールド名は **Draft モデル（`app.models.draft.Draft`）と一致**
  （`assignments`, `unassigned_students`, `violated_constraints`）
- ただし Phase 3.2 では `violated_constraints: list[str]`、Draft は `list[dict[str, Any]]`
  → Phase 3.4 でドラフト保存時に変換が必要（説明文を `{"message": "..."}` 形式に包む等）。
  もしくは Draft モデル側を `list[str]` に揃える検討（後方互換に注意）

### Phase 4.4a（日程案表示画面）

- マトリクス表示の入力は `SchedulingResult`。フィールド名はそのまま使える
- 違反制約の表示は文字列リスト（`list[str]`）を前提に。リッチな構造化が必要なら Phase 3.3a で見直す

## 未解決の課題・要確認事項

- **要確認**：`violated_constraints` を `list[str]` で返しているが、Draft モデルは
  `list[dict[str, Any]]`。Phase 3.4 でドラフト保存時のスキーマ整合をどう取るか
  （文字列 → `{"message": str}` でラップ vs Draft 側を `list[str]` に揃える）
- **要確認**：Python 3.14 ホイールが提供されていない ortools バージョンが
  CI/別環境に存在する可能性。`pyproject.toml` の制約は `>=9.10` で十分緩いが、
  実装者環境では `9.15.6755` を使った
- **保留**：CP-SAT のソルバ並列度（`num_search_workers`）はデフォルト（= CPU コア数の半分）。
  Phase 3.3b のパフォーマンス測定で必要に応じてチューニング
- **保留**：`time_limit_seconds=60` がプロトタイプ規模で十分かは Phase 3.3b で実測する。
  パフォーマンス目標（30 名・5 日 × 10 コマで 10 秒以内）に対して 60 秒は安全側
- **保留**：Availability の (date, start, end) が候補スロットと部分的にしか一致しない場合
  （例：候補スロット 16:00-16:20 / 16:20-16:40 に対して、生徒が 16:00-16:40 と「結合」した
  申告を返すケース）は現状無視される。Form のチェックボックスマトリクスが
  candidate_time_slots 単位で出る前提なので実害は無いが、Phase 2.3 のパースを
  バイパスして JSON を直接置く場合に注意
- **保留**：重複 `student_number` の Response が来た場合、最初の出現を採用しているが、
  `submitted_at` で最新を取る方が安全。Phase 2.3 の `list_latest_per_student` が
  既に最新版を返す前提なので実害は無い。防御として `max(by=submitted_at)` に変える検討
- **保留**：`pyproject.toml` の `ortools>=9.10` は実機で `9.15.6755` をインストールしている。
  CI で別バージョンになっても挙動が変わらないことは保証していない（CP-SAT API の
  破壊的変更は稀だが）。Phase 6.2 で `~=9.15` に締めるか検討
- **保留**：CP-SAT が UNKNOWN（タイムアウト等）を返した場合のフォールバックは
  「全員未配置 + 文言」だが、これは情報量が少ない。Phase 3.3b のタイムアウト処理で
  「部分解を保持しつつタイムアウト警告」とした方が UX 上は好ましい

## 動作確認手順（参考）

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_scheduler_hard.py -v
```

期待される出力:
```
14 passed in ~1 sec
```

REPL で直接呼び出す例:

```powershell
cd backend
.\.venv\Scripts\python.exe -c "
from datetime import date, datetime, time, timezone
from app.models import (Project, TimeSlot, Response, Availability, Rules,
                       GlobalConstraints, DurationMultiplierConstraint)
from app.services.scheduler import solve_hard

project = Project(
    project_id='demo', display_name='デモ',
    created_at=datetime(2026,1,1,tzinfo=timezone.utc), status='in_progress',
    slot_minutes=20,
    candidate_dates=[date(2026,7,15)],
    candidate_time_slots=[TimeSlot(start=time(16,0), end=time(16,20)),
                          TimeSlot(start=time(16,20), end=time(16,40))],
    student_numbers=[1, 2],
)
responses = [
    Response(project_id='demo', student_number=sn,
             submitted_at=datetime(2026,6,24,tzinfo=timezone.utc),
             google_form_response_id=f'r_{sn}',
             availability=[Availability(date=date(2026,7,15), start=time(16,0), end=time(16,20)),
                           Availability(date=date(2026,7,15), start=time(16,20), end=time(16,40))])
    for sn in [1,2]
]
rules = Rules(
    global_constraints=GlobalConstraints(max_consecutive_slots=10,
                                          forced_break_slots=0, max_slots_per_day=20),
    student_constraints=[],
)
print(solve_hard(project, responses, rules).model_dump_json(indent=2))
"
```

## 作成ファイル一覧

- `backend/app/services/scheduler.py`（新規）
- `backend/tests/test_scheduler_hard.py`（新規・14 件）
- `backend/pyproject.toml`（`ortools>=9.10` を追加）
- `docs/handoff_phase3_2.md`（本ドキュメント）
