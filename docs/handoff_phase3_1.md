# Phase 3.1 引き継ぎメモ

## サマリ

`FileRuleRepository` を本実装に置き換え、グローバルルールとプロジェクトルールの
CRUD API（`GET/PUT /api/global-rules`、`GET/PUT /api/projects/{id}/rules`）を実装した。

プロジェクト作成時のルール複製ロジックを Phase 2.1 の暫定実装
（`FileProjectRepository._initialize_project_rules`）から
API ハンドラ → `RuleRepository.copy_global_to_project()` 経由の本実装に移行した。

テストは TDD（RED → 10 件失敗を確認 → test commit → 実装 → 66 件全 PASS → GREEN commit）
の順序で進めた。

テスト総数：**既存 55 - 1 削除 + 12 新規 = 66 件、全 PASS**。

## 採用方式・決定事項

### 1. グローバルルール初期化タイミング

`GET /api/global-rules` は `global_rules.json` が存在しない場合（初回アクセス）に
`_DEFAULT_RULES` を書き出してから返す「書き込み初期化」方式を採用。

| 代替案 | 不採用理由 |
|---|---|
| ファイル不在時は in-memory のみで返す | 次回アクセス時も同じ既定値を返す保証がなく、整合性が崩れる |
| 起動時に必ず初期化 | lifespan を変更する必要があり、他フェーズへの影響が大きい |

`FileRuleRepository.get_global_rules()` → `set_global_rules(_DEFAULT_RULES)` → ファイル書き出しとリターン。

### 2. プロジェクト作成時のルール複製（Phase 2.1 → Phase 3.1 移管）

Phase 2.1 では `FileProjectRepository.create()` 内で `_initialize_project_rules()` が
直接 `config_dir/global_rules.json` を読んでいた（Repository 間の非疎結合）。

Phase 3.1 では以下のように改善した：

```
create_project (API ハンドラ)
  ↓ repo.create(project)          ← ディレクトリ構造生成のみ、rules.json は生成しない
  ↓ rule_repo.copy_global_to_project(project_id)  ← RuleRepository が担当
```

- `FileProjectRepository._initialize_project_rules()` を削除
- `FileProjectRepository.create()` から `_initialize_project_rules()` 呼び出しを除去
- `create_project` ハンドラに `RuleRepository` を DI 注入（`Depends(get_rule_repository)`）
- 既存の `test_create_project_creates_directory_and_files` は API 経由なので影響なし（rules.json がハンドラ層で生成される）

### 3. バリデーション方式

重み範囲（0〜10）および制約タイプは Pydantic モデル（`backend/app/models/rules.py`）で
宣言済み（Phase 1.2）。API ハンドラ側は追加バリデーション不要。
不正値は FastAPI が 422 を自動返答する。

### 4. API エンドポイント設計

| メソッド | パス | レスポンスモデル | エラー |
|---|---|---|---|
| GET | `/api/global-rules` | `Rules` | （常に 200）未設定時は既定値で初期化 |
| PUT | `/api/global-rules` | `Rules` | 422（バリデーション失敗） |
| GET | `/api/projects/{id}/rules` | `Rules` | 404（プロジェクト/rules.json 不在） |
| PUT | `/api/projects/{id}/rules` | `Rules` | 404（プロジェクト不在）/ 422（バリデーション失敗） |

`rules_router` を `APIRouter(tags=["rules"])` で定義し、プレフィックスなし（パス全体を
各デコレータに書く）。`main.py` で `application.include_router(rules_router)` に追加済み。

### 5. repository 間疎結合の改善

Phase 2.3 の引き継ぎに記載されていた「`FileResponseRepository.get_pending_student_numbers`
が `project.json` を直接読む非疎結合性」については、Phase 3.1 スコープ外として
今回は手を付けない。Phase 3.1 は Rule 管理に集中した。

## 主要な実装上のパラメータ

| 項目 | 値 | 備考 |
|---|---|---|
| グローバルルール保存先 | `<config_dir>/global_rules.json` | `FileRuleRepository.GLOBAL_RULES_FILE_NAME` |
| プロジェクトルール保存先 | `<projects_dir>/<project_id>/rules.json` | `FileRuleRepository.RULES_FILE_NAME` |
| 既定値 `_DEFAULT_RULES` | `max_consecutive_slots=4, forced_break_slots=1, max_slots_per_day=20, teacher_unavailable=[], student_constraints=[]` | モジュールレベル定数のまま保持 |
| 重み範囲 | `WEIGHT_MIN=0 〜 WEIGHT_MAX=10` | `backend/app/models/rules.py` |
| 制約タイプ | `pairing / avoid_time / prefer_time / duration_multiplier` | discriminated union |
| テスト総数 | 既存 55 - 1 + 12 = **66 件** | 全 PASS |

## 主要ファイル

### 新規

- `backend/app/api/rules.py`：ルール管理ルータ
  - `get_global_rules` / `put_global_rules`
  - `get_project_rules` / `put_project_rules`
- `backend/tests/test_rules_api.py`：API テスト 12 件

### 変更

- `backend/app/repositories/file_repository.py`
  - `FileRuleRepository` を本実装に（`get_global_rules / set_global_rules / get_project_rules / set_project_rules / copy_global_to_project` の 5 メソッド）
  - `FileProjectRepository.create()` から `_initialize_project_rules()` 呼び出しを除去
  - `FileProjectRepository._initialize_project_rules()` メソッドを削除
  - `_DEFAULT_RULES` はモジュールレベルに保持（`FileRuleRepository.get_global_rules()` のフォールバックに使用）
- `backend/app/api/projects.py`
  - `create_project` ハンドラに `RuleRepository` DI を追加（`Depends(get_rule_repository)`）
  - `rule_repo.copy_global_to_project(created.project_id)` 呼び出しを追加
- `backend/app/main.py`
  - `rules_router` を `include_router` で登録
- `backend/tests/test_repositories.py`
  - `test_rule_repository_methods_raise_not_implemented` を削除（コメントで経緯を記載）

### Phase 1.x / 2.x からの無変更

- `backend/app/models/rules.py`（モデル変更なし）
- `backend/app/repositories/base.py`
- `backend/app/dependencies.py`
- `backend/app/config.py`
- `backend/tests/conftest.py`
- 他の既存テストファイル
- `scripts/*.ps1`, `backend/pyproject.toml`, `.gitignore`, `.gitattributes`

## コミット履歴

```
66c38ca feat(phase3.1): implement FileRuleRepository and rules api endpoints (GREEN)
3e0d413 test(phase3.1): add rules api test cases (RED)
```

（注: 当初の実装コミットは `41dbfaa` / `67fd27a` だったが、Check-PhaseDone.ps1 の
`audit_trail_integrity` 検査要件を満たすため、ユーザー承認のもと commit chain を
cherry-pick で再構築。テスト・実装内容は無変更。）

RED コミット時点で 10 件失敗（`GET /PUT /api/global-rules` / `GET /PUT /api/projects/{id}/rules`
いずれも 404 Not Found）を確認した上で test commit を打ち、実装で全 PASS に持ち込んだ。

## 後続サブステップへの引き継ぎ事項

### Phase 3.2（スケジューラ・ハード制約）

- スケジューラへの入力となるルールは `FileRuleRepository.get_project_rules(project_id)` で取得可能
- `Rules.global_constraints.teacher_unavailable: list[TeacherUnavailable]` がハード制約の教師不可時間帯
- `Rules.student_constraints` は `StudentConstraint` の discriminated union（`type` フィールドで判別）
- `DurationMultiplierConstraint`（`type="duration_multiplier"`）はハード制約（requirements.md §4.6.2）
- `PairingConstraint / AvoidTimeConstraint / PreferTimeConstraint` はソフト制約（重み付きペナルティ）

### Phase 3.3a / 3.3b（スケジューラ・ソフト制約と API 統合）

- ソフト制約の重みは `weight: int (0〜10)`。`weight=0` の場合はペナルティなし（無視）
- `AvoidTimeConstraint` は `avoid_after` と `avoid_before` の両方を持つが、どちらか一方のみ使うケースが多い
  （Phase 1.2 引き継ぎ「両方 None / 両方指定」の許容問題は未解決・保留）
- `PreferTimeConstraint` も同様に `prefer_before` / `prefer_after` の組合せ

### Phase 3.4（ドラフト保存・ロック）

- プロジェクトルールの参照方法は `FileRuleRepository.get_project_rules(project_id)` で統一

### Phase 4.2 / 4.3（フロントエンド）

- グローバルルール設定画面：`GET /api/global-rules` + `PUT /api/global-rules`
- プロジェクトルール設定画面：`GET /api/projects/{id}/rules` + `PUT /api/projects/{id}/rules`
- レスポンスモデルは `Rules` スキーマ（requirements.md §3.2 の `rules.json` と同一）

## 未解決の課題・要確認事項

- **保留**：`FileResponseRepository.get_pending_student_numbers` が `project.json` を
  直接読む非疎結合性（Phase 2.3 引き継ぎ記載）は未対応のまま。Phase 3.2 / 3.4 の
  スコープで改善機会があれば検討する
- **保留**：`AvoidTimeConstraint` / `PreferTimeConstraint` で `avoid_after` / `avoid_before`
  の両方が None または両方が指定されたケースのバリデーションが未実装
  （Phase 1.2 引き継ぎからの継続）。Phase 3.3a のソフト制約実装時に追加検討
- **保留**：`_DEFAULT_RULES` の既定値は requirements.md §3.2 のサンプルに近い値
  （`max_consecutive_slots=4, max_slots_per_day=20`）。実際の運用に合わせた調整は
  フロントエンドの UI（Phase 4.2 ホーム画面のグローバルルール設定）で可能

## 最終コミットハッシュ

```
66c38ca1cd9b215a5c19204e5e6ded2efba65b31  feat(phase3.1): implement FileRuleRepository and rules api endpoints (GREEN)
```

（cherry-pick 再構築前の元 hash: `41dbfaa88b3053dc8479e00557d20e01c4690087`）
