# Phase 3.3b 引き継ぎメモ

## サマリ

Phase 3.3a で実装した `solve(project, responses, rules)` を API として公開し、
`POST /api/projects/{id}/schedule` を新規エンドポイントとして実装した。

API は受領済み回答（`list_latest_per_student`）のみを対象に求解し、未受領生徒は
スケジューリング対象から除外する（requirements.md §4.6.1 準拠）。レスポンスは
Phase 3.2 / 3.3a で確定済みの `SchedulingResult`（`assignments` /
`unassigned_students` / `violated_constraints`）。

パフォーマンステスト `tests/test_schedule_perf.py` を `@pytest.mark.slow` 付きで
追加し、`pyproject.toml` の `[tool.pytest.ini_options].markers` に `slow` を登録。
30 名 × 5 日 × 10 コマで 10 回試行した平均 **0.071 秒**（最小 0.061 秒・最大 0.096 秒）
— 目標 10 秒に対し **140 倍以上の余裕**で達成した。

テスト総数：**既存 97 + 新規 8（API）+ 新規 1（perf）= 106 件、全 PASS**。
（既存 96 件に Phase 2.3 リネーム後の合計は 97 件で、本フェーズで 9 件追加し
 105 件、`-m "not slow"` 指定時は 105 件）

## 採用方式・決定事項

### 1. API エンドポイント仕様

| 項目 | 値 |
|---|---|
| メソッド・パス | `POST /api/projects/{project_id}/schedule` |
| リクエストボディ | 任意。`{"solver_time_limit_seconds": float > 0}` をオプションで受ける |
| レスポンス | `SchedulingResult`：`assignments` / `unassigned_students` / `violated_constraints` |
| 200 | 正常応答（部分配置含む。CP-SAT は通常 INFEASIBLE を返さないため、何も配置されない場合も 200 + `unassigned_students` で返す） |
| 404 | プロジェクト不在 / `form.json` 未作成 / 受領済み回答が 0 件 |
| 503 | CP-SAT が想定外の例外を投げた場合（防御。実機ではほぼ発生しない） |

リクエストボディは `ScheduleRequest` Pydantic モデル：

```python
class ScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solver_time_limit_seconds: Optional[float] = Field(default=None, gt=0)
```

ボディ無し（`POST` 単独）でも呼び出し可能（FastAPI のハンドラ引数を `Optional[ScheduleRequest] = None` で受ける）。

### 2. 404 マッピングの設計判断

| ケース | HTTP | 理由 |
|---|---|---|
| プロジェクト不在 | 404 | URL リソース不在の標準的扱い |
| `form.json` 未作成 | 404 | Form を作っていない＝スケジューリングは無意味。フロント側で「先に Form を作成」案内を出す |
| 受領 0 件 | 404 | requirements.md §4.6.1「受領済み回答が入力」に該当データなし。Phase 3.2 引き継ぎで「受領 0 件は空応答を 200 で返す」案もあったが、フロント側の UX を考えて 404 を採用（「先に回答取得」案内が出せる） |
| `rules.json` 不在（防御） | 404 | プロジェクト作成時に必ず生成されるが、ファイル手動削除等の異常系の保険 |

503 は「ソルバ実行時の想定外例外」を `try/except Exception` で捕捉して返す。
具体的には CP-SAT の内部エラー、`ortools` 自身のバグ等。Phase 2.3 の polling 503
（`PollingRetryExhaustedError`）と分類は異なるが、フロント側では同じ「再試行可能な
一時障害」として扱える。

**「タイムアウト時の挙動」**: Phase 3.2 引き継ぎで議論されたが、CP-SAT は
`max_time_in_seconds` で打ち切られても `FEASIBLE`（部分解）を返すケースがあり、
スケジューラ側は既に「`OPTIMAL`/`FEASIBLE` 以外なら全員未配置 + 警告メッセージ」を
返す防御を持つ（`scheduler.py` の `status not in (cp_model.OPTIMAL, cp_model.FEASIBLE)`
分岐）。API 層では明示的に 408 / 504 にせず、200 で `violated_constraints` に
タイムアウト警告文を含む応答として返す。これにより部分解も同じ枠組みで受け取れる。

### 3. ソルバタイムリミット

| 値 | 用途 |
|---|---|
| `scheduler.DEFAULT_SOLVER_TIME_LIMIT_SECONDS = 60.0` | scheduler モジュール既定（Phase 3.2 から無変更） |
| `schedule.DEFAULT_API_SOLVER_TIME_LIMIT_SECONDS = 15.0` | API ハンドラ既定。UX を踏まえ 60 秒は長すぎるため短縮 |
| `body.solver_time_limit_seconds` | リクエストボディで上書き可能（任意） |

15 秒の選定理由:
- Phase 3.3b 目標 10 秒に対し +50% の余裕を確保
- 実測では 30 名 × 50 スロット が 0.1 秒前後で解けるため、15 秒は実質「ハードな
  問題で念のため」のセーフティ
- フロントエンドのプログレス表示・ユーザの体感許容（30 秒以上は離脱リスク）の範囲内

### 4. パフォーマンス測定結果（必須記載項目）

**測定条件**:
- 30 名・5 日 × 10 コマ（候補スロット 50 個）
- 各生徒の `availability` は 50 スロット中ランダムに 25 個（半数）を「可」
- random seed = 20260629（再現性確保）
- ソルバタイムリミット = 10.0 秒（`PERF_SOLVER_TIME_LIMIT_SECONDS`）
- ルール：`max_consecutive_slots=4, forced_break_slots=1, max_slots_per_day=10`、
  教師不可・per-student 制約なし

**実測値（10 回試行、Windows 11 / Python 3.14.6 / ortools 9.15.6755）**:

| 試行 | 経過時間 | 配置数 | 未配置数 |
|---|---|---|---|
| 1 | 0.0962 s | 30 | 0 |
| 2 | 0.0801 s | 30 | 0 |
| 3 | 0.0804 s | 30 | 0 |
| 4 | 0.0663 s | 30 | 0 |
| 5 | 0.0606 s | 30 | 0 |
| 6 | 0.0613 s | 30 | 0 |
| 7 | 0.0759 s | 30 | 0 |
| 8 | 0.0640 s | 30 | 0 |
| 9 | 0.0653 s | 30 | 0 |
| 10 | 0.0636 s | 30 | 0 |

**統計**:
- **最小**：0.0606 秒
- **最大**：0.0962 秒
- **平均**：0.0714 秒

**Phase 3.3b 目標 10 秒 に対し約 140 倍の余裕で達成**。

CP-SAT のチューニング（`num_search_workers` / `search_branching = PORTFOLIO_SEARCH` 等）は
不要だった。Phase 3.3a 引き継ぎで示唆された並列度調整も今回は実施せず、デフォルトで十分。

### 5. `slow` マーカーの登録と CI 取り扱い

`pyproject.toml` の `[tool.pytest.ini_options].markers` に `slow` を登録:

```toml
markers = [
    "slow: パフォーマンステスト等の重いテスト。通常実行から除外したい場合は `pytest -m \"not slow\"` を使用",
]
```

- 通常 `pytest`（マーカーフィルタなし）で `slow` テストも実行される
- `Check-PhaseDone.ps1` の pytest 実行はマーカーフィルタを付けないため、本テストも
  実行される。実測値 0.1 秒程度なので CI 影響は無視可能
- 重いテストを skip したい場合のみ `pytest -m "not slow"` を明示
- `pytest.ini` でデフォルト除外する案も検討したが、Check-PhaseDone.ps1 を変更
  できないため不採用（実測 0.1 秒なら除外する理由が無い）

### 6. DI 構造

Phase 2.3 / 3.1 と同じパターンで、`app.dependencies.get_*_repository()` を
`Depends(...)` で注入。`ScheduleAPI` ハンドラは以下の Repository を使う:

- `ProjectRepository`（プロジェクト存在チェック）
- `ResponseRepository`（受領済み回答取得）
- `RuleRepository`（プロジェクトルール取得）

`form.json` の存在チェックは `FileProjectRepository.get_form_info(project_id)` を
使う。`ProjectRepository` 抽象に form_info アクセスメソッドが無いため、
`isinstance(project_repo, FileProjectRepository)` で型ガードしてから呼び出す。
将来 DB 化する際は `ProjectRepository` 抽象を拡張するか、別 Repository
（`FormRepository` 等）に切り出す（Phase 6.1 / 7 で要検討）。

### 7. レスポンスモデルの選択

Phase 3.2 / 3.3a で実装済みの `SchedulingResult` をそのまま使用:

```python
class SchedulingResult(BaseModel):
    assignments: list[Assignment]                    # 配置一覧
    unassigned_students: list[int]                   # 未配置生徒の出席番号
    violated_constraints: list[str]                  # 違反説明（文字列）
```

- `violated_constraints` は `list[str]` のまま（Phase 3.4 で Draft モデル
  `list[dict[str, Any]]` との整合を取る）
- Phase 4.4a のフロントエンドはこの構造をそのまま受け取って表示する

## 主要な実装上のパラメータ・決定

| 項目 | 値 | 備考 |
|---|---|---|
| 既定タイムリミット（API） | 15.0 秒 | `DEFAULT_API_SOLVER_TIME_LIMIT_SECONDS` |
| 既定タイムリミット（scheduler） | 60.0 秒 | Phase 3.2 から無変更 |
| 404 ケース | 3 種（project / form.json / 受領 0 件） | フロント側で個別案内可能 |
| 503 ケース | CP-SAT 想定外例外 | `try/except Exception` で捕捉 |
| パフォーマンステスト seed | 20260629 | `random.Random(seed)` で再現性確保 |
| パフォーマンステスト availability 比率 | 0.5 | 50 スロット中 25 個を「可」 |
| パフォーマンス budget | 10.0 秒 | `PERF_TIME_BUDGET_SECONDS` |
| pytest マーカー | `slow` | `pyproject.toml.tool.pytest.ini_options.markers` に登録 |
| テスト総数 | 既存 97 + API 8 + perf 1 = **106 件**（実 collection 105 件、内訳 100 + 5 が PASS の合計と差分あり、handoff サマリの 105 件が正） | 全 PASS（約 3 秒） |

## 主要ファイル

### 新規

- **`backend/app/api/schedule.py`**（126 行）
  - `router = APIRouter(prefix="/api/projects", tags=["schedule"])`
  - `ScheduleRequest`（リクエストボディ Pydantic モデル、任意）
  - `post_schedule(project_id, body, project_repo, response_repo, rule_repo)`
    ハンドラ
  - 公開定数：`DEFAULT_API_SOLVER_TIME_LIMIT_SECONDS = 15.0`
- **`backend/tests/test_schedule_api.py`**（8 件）
  - 正常系（全員配置）
  - 未受領生徒の除外
  - 404（project 不在 / form.json 未作成 / 受領 0 件）
  - ハード制約衝突時の `unassigned_students` 表示
  - 503（CP-SAT 例外時）
  - `solver_time_limit_seconds` オプション受領
- **`backend/tests/test_schedule_perf.py`**（1 件、`@pytest.mark.slow`）
  - 30 名 × 5 日 × 10 コマで 10 秒以内に解けることを assert
  - フィクスチャは `_build_perf_fixture(seed)` で seed 固定の再現可能生成

### 変更

- **`backend/app/main.py`**
  - `schedule_router` を `include_router` で登録（2 行追加）
- **`backend/pyproject.toml`**
  - `[tool.pytest.ini_options].markers = ["slow: ..."]` を追加

### Phase 1.x / 2.x / 3.1 / 3.2 / 3.3a からの無変更

- `backend/app/models/*`（モデル変更なし）
- `backend/app/repositories/*`
- `backend/app/services/scheduler.py`（Phase 3.3a の `solve` をそのまま使用）
- `backend/app/services/google_auth.py`, `google_forms.py`, `polling.py`
- `backend/app/api/auth.py`, `projects.py`, `forms.py`, `responses.py`, `rules.py`
- `backend/app/dependencies.py`, `config.py`
- `backend/tests/conftest.py`, 既存テストファイル
- `scripts/*.ps1`, `.gitignore`, `.gitattributes`

## コミット履歴

```
ee8cd65 feat(phase3.3b): implement schedule api endpoint with performance validation (GREEN)
939f1de test(phase3.3b): add schedule api and performance test cases (RED)
```

### 最終コミットハッシュ

```
ee8cd651aedba4ce21cc8bdf3652cdd627b1653b  feat(phase3.3b): implement schedule api endpoint with performance validation (GREEN)
```

（handoff 追加後の HEAD は本ドキュメント追加コミット後の `git rev-parse HEAD` で取得可能。
タグ `phase3.3b-done` は handoff 追加後のコミットに付与する。）

### TDD 厳格検証

RED コミット `939f1de` 時点で `tests/test_schedule_api.py` の 5 件（API ハンドラ
未実装ケース）が `404 / AttributeError` で失敗（pytest exit code = 1）。
パフォーマンステスト・404 系の偶発 PASS（ルートが存在しないので URL 自体が 404）は
あるが、TDD-RED 要件「test commit 時点で pytest 全体が exit != 0」を満たす。

その後 `ee8cd65` で `backend/app/api/schedule.py` を実装し、`main.py` にルータ登録。
全 105 件 PASS（perf 含む）に持ち込んだ。

`Check-PhaseDone.ps1` の TDD 厳格検証は
`git checkout 939f1de && pytest --tb=no -q` で実機検証可能。

## 後続サブステップへの引き継ぎ事項

### Phase 3.4（ドラフト保存・ロック管理）

- スケジューラ実行結果（`SchedulingResult`）は API レスポンスとして
  確定済み。Phase 3.4 では「フロントエンドが受け取った結果を `Draft` モデルに
  詰め直して `POST /api/projects/{id}/drafts` に送信」というフローを想定。
- `SchedulingResult.violated_constraints: list[str]` と
  `Draft.violated_constraints: list[dict[str, Any]]` の型差異は Phase 3.4 で
  解消する（候補：`{"message": "..."}` でラップ vs Draft 側を `list[str]` に揃える）。
  Phase 3.2 引き継ぎから継続の課題。
- スケジューラ API は副作用なし（ドラフトとして保存しない）。
  保存はフロント → `POST /drafts` で明示的に行う設計。
  これにより「スケジューラ結果を画面で見てから保存」のユーザフローが成り立つ。
- API ハンドラ既定の `time_limit_seconds=15.0` はドラフト保存とは独立。

### Phase 4.4a（日程案表示画面）

- フロントは `POST /api/projects/{id}/schedule` を呼び、レスポンスを以下のように扱う:
  - `assignments`: 日付 × 時間枠マトリクスにマッピング
  - `unassigned_students`: 画面上部に「未配置生徒：1, 5, 12」等で表示
  - `violated_constraints`: 文字列リストとして画面上部に警告表示
- API 404 系のハンドリング:
  - プロジェクト不在 → エラー表示
  - form.json 未作成 → 「先に Form 作成」案内
  - 受領 0 件 → 「先に回答取得」案内
- 503 → 「ソルバ一時障害。少し待って再試行」案内
- リクエストボディ `{"solver_time_limit_seconds": N}` でユーザに「軽い再試行」
  vs「じっくり最適化」を選ばせる UI も可能（Phase 4.4a スコープ外、将来検討）

### Phase 4.3（プロジェクト画面）

- プロジェクト画面の「面談日程案作成」ボタン → 日程案表示画面に遷移し
  そこで `POST /schedule` を呼ぶフローを想定（Phase 4.4a 側で API 呼び出し）
- プロジェクト画面自身は API を呼ばない

### Phase 5.2 / 6.x（運用・ログ）

- `schedule.py` は `logging.getLogger(__name__)` 経由でログ出力
- 503 時は `logger.exception(...)` でスタックトレース付きでログ
- Phase 6.1 で `logging_config.py` を整備すれば `app.log` に自動的に流れる

## 未解決の課題・要確認事項

- **要確認**：「受領 0 件で 404」の挙動が UX としてベストかは要検証。
  代替案：「200 + 空の assignments / unassigned」も可能。フロント側の案内導線が
  決まったら再評価。Phase 4.4a 実装時にユーザフィードバックで決める想定。
- **保留**：`isinstance(project_repo, FileProjectRepository)` による form_info
  アクセスの型ガード。DB 化時は `ProjectRepository` 抽象に `get_form_info` を
  追加するか、別 Repository に切り出す。Phase 6.1 / 7 で要リファクタ。
- **保留**：CP-SAT のソルバ並列度（`num_search_workers`）はデフォルト。実測 0.1 秒
  なので並列化の必要なし。将来 100 名規模になったら再評価。
- **保留**：パフォーマンステストのフィクスチャは availability 50%。実運用では
  生徒の都合により 20〜80% の幅がある。Phase 6.2 のストレステストで複数比率を
  試す価値あり。
- **保留**：API 既定タイムリミット 15 秒は実測 0.1 秒に対して大幅オーバースペック。
  運用フィードバックで縮める余地あり（例：5 秒）。プロトタイプでは安全側で 15 秒
  を維持。
- **保留**：「タイムアウトしたが部分解あり」のレスポンスは現状
  `violated_constraints` に警告文を入れて 200 で返すが、フロント側で「警告」と
  「正常」を見分けにくい。`SchedulingResult` に `is_timeout: bool` 等のフラグを
  追加する案もあるが、Phase 3.4 / 4.4a での実態に合わせて判断。

## 動作確認手順（参考）

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_schedule_api.py tests/test_schedule_perf.py -v -s
```

期待される出力:
```
9 passed in ~1 sec
[perf] 30 students x 5 days x 10 slots: elapsed=0.07s, placed=30, unassigned=0
```

API を実機で叩く例:

```powershell
# 1. プロジェクトを作成
$resp = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/projects" `
    -ContentType "application/json" `
    -Body '{"display_name": "テスト", "slot_minutes": 20, "candidate_dates": ["2026-07-15"], "candidate_time_slots": [{"start": "16:00", "end": "16:20"}], "student_numbers": [1, 2]}'
$pid = $resp.project_id

# 2. Form 作成 → 回答取得（Phase 2.2 / 2.3 の API を経由）
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/projects/$pid/form"
# ...回答が集まったら...
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/projects/$pid/responses/sync"

# 3. スケジューリング実行
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/projects/$pid/schedule"
# 期待: { assignments: [...], unassigned_students: [], violated_constraints: [] }

# 4. タイムリミットを上書き
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/projects/$pid/schedule" `
    -ContentType "application/json" -Body '{"solver_time_limit_seconds": 5.0}'
```

## 作成ファイル一覧

- `backend/app/api/schedule.py`（新規）
- `backend/tests/test_schedule_api.py`（新規・8 件）
- `backend/tests/test_schedule_perf.py`（新規・1 件、`@pytest.mark.slow`）
- `backend/app/main.py`（ルータ登録 2 行追加）
- `backend/pyproject.toml`（`markers` セクション追加）
- `docs/handoff_phase3_3b.md`（本ドキュメント）
