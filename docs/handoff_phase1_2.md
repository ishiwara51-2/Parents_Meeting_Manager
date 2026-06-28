# Phase 1.2 引き継ぎメモ

## サマリ

`requirements.md §3.2` のデータスキーマを Pydantic v2 モデルとして実装し、
データアクセス層を Repository パターンの抽象基底（ABC）＋ファイルベース実装の
骨格として整備した。具象メソッドは `raise NotImplementedError` のスケルトンで、
後続フェーズ（2.1 / 2.3 / 3.1 / 3.4）で本実装に置き換える。

FastAPI 依存性注入の仕組みを `backend/app/dependencies.py` に追加し、
Repository を `Depends(...)` で注入できるようにした。

## 採用方式・決定事項

### モデルのファイル分割

`backend/app/models/` 配下にエンティティ単位でファイルを分割し、`__init__.py`
で再エクスポートする。

| ファイル | クラス | requirements.md 対応 |
|---|---|---|
| `project.py` | `Project`, `TimeSlot`, `ProjectStatus` | §3.2 project.json |
| `rules.py` | `Rules`, `GlobalConstraints`, `TeacherUnavailable`, 4種の生徒別制約 | §3.2 rules.json / §4.5 / §4.6.2 |
| `response.py` | `Response`, `Availability` | §3.2 responses/.../*.json |
| `draft.py` | `Draft`, `Assignment` | §3.2 drafts/draft_*.json |
| `form.py` | `FormInfo` | §3.1 form.json（最小限） |

### Pydantic v2 の field 名衝突対応

`Availability.date`, `Assignment.date`, `TeacherUnavailable.date` の3箇所で
field 名 `date` が型注釈の `date` と衝突し `PydanticUserError: Make sure you
don't have any field name clashing with a type annotation` が発生する。

回避策として **`import datetime as _dt`** を導入し、フィールドの型注釈側を
`_dt.date` に変更した（field 名は requirements.md §3.2 の JSON キーと一致させる
ため `date` のまま）。`time` は field 名と衝突しないのでそのまま使用。

```python
import datetime as _dt
from datetime import time

class Availability(BaseModel):
    date: _dt.date  # field 名はスキーマ通り 'date' のまま
    start: time
    end: time
```

### 生徒別制約の discriminated union

`StudentConstraint` は `type` フィールドを discriminator とした `Annotated[Union[...], Field(discriminator="type")]` で表現。
将来 `avoid_time` 系で `avoid_before` を使いたいケースに備え、`avoid_after` / `avoid_before` の双方を `Optional[time]` として持つ（requirements.md §3.2 の例には `avoid_after` のみだが片方は将来拡張用）。

`duration_multiplier` は requirements.md §4.6.2 でハード制約に分類されているため `weight` を持たず、`multiplier: int (>=1)` のみ持つ。

### Repository 抽象化の構造

```
ProjectRepository (ABC)         FileProjectRepository (Phase 2.1 で実装)
RuleRepository (ABC)            FileRuleRepository    (Phase 3.1 で実装)
ResponseRepository (ABC)        FileResponseRepository (Phase 2.3 で実装)
DraftRepository (ABC)           FileDraftRepository   (Phase 3.4 で実装)
```

ファイル実装は `_SettingsBacked` mixin を継承し、`settings.projects_dir` /
`settings.config_dir` を `self.projects_dir` / `self.config_dir` プロパティで
公開する。具象実装は後続フェーズでこれらの基底パスから JSON ファイル操作を行う。

### DI 設計

`backend/app/dependencies.py` のプロバイダ関数：

| プロバイダ | 戻り値型（宣言） | 既定実装 |
|---|---|---|
| `get_settings_dependency()` | `Settings` | `get_settings()` シングルトン |
| `get_project_repository()` | `ProjectRepository` | `FileProjectRepository(get_settings())` |
| `get_rule_repository()` | `RuleRepository` | `FileRuleRepository(get_settings())` |
| `get_response_repository()` | `ResponseRepository` | `FileResponseRepository(get_settings())` |
| `get_draft_repository()` | `DraftRepository` | `FileDraftRepository(get_settings())` |

戻り値の型注釈を**抽象基底**にしたのは、`app.dependency_overrides[get_project_repository] = lambda: stub` 形式で具象を差し替えやすくするため（requirements.md §6 末尾「ファイルベース実装を後でDB実装に差し替え可能にする」）。

## 主要な実装上のパラメータ

| 項目 | 値 | 備考 |
|---|---|---|
| Pydantic バージョン | v2 系（`>=2`） | `pyproject.toml` 既存依存 |
| 重み範囲 | 0〜10 | requirements.md §4.5.2 を `WEIGHT_MIN/WEIGHT_MAX` 定数化 |
| `model_config` 既定 | `extra="forbid"` | スキーマ外フィールドの混入を禁止 |
| `FormInfo` のみ | `extra="allow"` | Phase 2.0 の調査で追加フィールドが入る可能性に備える |
| Repository の状態 | 全メソッド `NotImplementedError` | クラス docstring に担当 Phase を明記 |
| テスト総数 | 既存 2 + 新規 18 = 20件 | 全 PASS |

## 主要ファイル

### 新規

- `backend/app/models/project.py`
- `backend/app/models/rules.py`
- `backend/app/models/response.py`
- `backend/app/models/draft.py`
- `backend/app/models/form.py`
- `backend/app/repositories/base.py`：4つの ABC
- `backend/app/repositories/file_repository.py`：4つの File*Repository（骨格）
- `backend/app/dependencies.py`：DI プロバイダ
- `backend/tests/test_repositories.py`：スモークテスト18件

### 既存からの変更

- `backend/app/models/__init__.py`：再エクスポートに変更
- `backend/app/repositories/__init__.py`：再エクスポートに変更

### Phase 1.1 から無変更

- `backend/app/main.py` / `backend/app/config.py`
- `backend/tests/conftest.py` / `backend/tests/test_health.py`
- `scripts/setup.ps1` / `scripts/start-dev.ps1`
- `.gitignore` / `.gitattributes` / `backend/pyproject.toml`

## コミット履歴

```
ab7c03f feat(phase1.2): add DI providers and repository smoke tests
d4d33c2 feat(phase1.2): add repository ABC and file-based skeleton
066b64f feat(phase1.2): add pydantic models for project/rules/response/draft/form
```

## 後続サブステップへの引き継ぎ事項

### Phase 2.1（プロジェクト管理 API）

- 既存の `FileProjectRepository` 骨格を本実装に置き換える。`_SettingsBacked` プロパティ（`self.projects_dir`）から `<APP_DATA_ROOT>\projects\<project_id>` を組み立てる
- プロジェクト作成時のサブディレクトリ（`responses/`, `drafts/`, `output/`）作成は `FileProjectRepository.create()` の責務
- グローバルルールの `rules.json` 複製は `FileRuleRepository.copy_global_to_project()` を呼び出す形を想定（依存方向：`FileProjectRepository` → `RuleRepository`）。両者の調停はサービス層 or API ハンドラで行う
- `Project.created_at` は TZ 付き `datetime`。プロジェクト一覧の作成日時降順ソートはここを基準にする
- API ハンドラは `Depends(get_project_repository)` で Repository を注入

### Phase 2.3（回答ポーリング）

- `FileResponseRepository.get_known_form_response_ids()` でポーリング重複検知（既存 `responseId` を集合で返す）
- 保存先パスは `<project_dir>\responses\<出席番号>\<YYYYMMDD_HHMMSS>.json`。タイムスタンプ形式は statically 文字列で組み立てる（`datetime.strftime("%Y%m%d_%H%M%S")` を想定）
- `Response.availability` は `list[Availability]`。マトリクスからのパースは `app.services.polling` 側の責務

### Phase 3.1（ルール管理 API）

- `FileRuleRepository` を本実装に。グローバルルールの初期既定値は requirements.md §3.2 のサンプル相当を採用するか、メインエージェントに確認
- バリデーション（重み範囲・タイプ）は既に Pydantic モデル側で行うため、Repository では JSON 読み書きと既定値生成のみに集中できる
- `copy_global_to_project()` は Phase 2.1 のプロジェクト作成時に呼ばれる前提

### Phase 3.4（ドラフト保存・ロック）

- `Draft.locked: bool` は永続化対象。`save_draft` 時に `True`、`unlock_latest` で `False` に書き換える
- `violated_constraints` は本フェーズで `list[dict[str, Any]]` プレースホルダ。Phase 3.2 / 3.3 でスケジューラ側の違反情報構造が確定したら、`Draft` モデルを置換または専用モデルに格上げする
- 過去ドラフトはファイル残置（requirements.md §4.9）。`list_all` は新しい順

### 共通

- すべての Repository は **抽象基底型**で受け取ること（`def handler(repo: ProjectRepository = Depends(get_project_repository))`）。`FileProjectRepository` を直接型に書かない
- パス操作は `pathlib.Path` のみ。文字列リテラルで `\` `/` を書かない（requirements.md §3.3 / §8.1）

## 未解決の課題・要確認事項

- **保留**：`FormInfo` の詳細フィールド（質問項目構造、マトリクス vs 複数選択の表現）は Phase 2.0 の Forms API 仕様調査結果を待つ。本フェーズでは `extra="allow"` で拡張余地を残してある
- **保留**：`Draft.violated_constraints[]` の要素スキーマは Phase 3.2 / 3.3 のスケジューラ実装と合わせて確定する。現状は `list[dict[str, Any]]` のプレースホルダ
- **要確認**：`AvoidTimeConstraint` / `PreferTimeConstraint` で「`avoid_after` と `avoid_before` の両方が None」「両方が指定」のケースを許容するか。現状モデルは両方任意（`time | None`）として通過させ、バリデーションは将来 Phase 3.3a のソフト制約実装時に追加することを想定
- **保留**：`Availability.start`/`Availability.end` と `TimeSlot.start`/`TimeSlot.end` を「片方が他方を参照する制約」（例：start < end）は未実装。Phase 2.3 / 3.1 のテスト整備時に追加検討

## 最終コミットハッシュ

実装3コミット（モデル / Repository骨格 / DI+テスト）の最終ハッシュ：

```
ab7c03f36f10c472f5fd83cc874214f9a09083df  feat(phase1.2): add DI providers and repository smoke tests
d4d33c2                                  feat(phase1.2): add repository ABC and file-based skeleton
066b64f                                  feat(phase1.2): add pydantic models for project/rules/response/draft/form
```

本ドキュメント追加後の HEAD ハッシュは `git rev-parse phase1.2-done` で取得可能（タグ `phase1.2-done` がこのコミットを指す）。
