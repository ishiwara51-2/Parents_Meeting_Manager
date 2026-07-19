"""Google Form メタ情報モデル（``form.json`` スキーマ）。

requirements.md §3.1 / §4.3 / §5.1、`docs/forms_api_research.md` §8、
`docs/handoff_phase2_0.md` で確定した **matrix 方式** の Form を Phase 2.2 で
生成・保存するための Pydantic モデル。

Phase 1.2 で配置した骨格（``project_id`` / ``created_at`` を持つ最小スキーマ）を
Phase 2.2 の実装方針（Phase 2.3 のポーリングで使うマッピング情報を保持）に
合わせて差し替えている。

``form.json`` は ``<project_dir>/form.json`` に保存され、Phase 2.3
（回答ポーリング）で各回答を「候補日 → 行 questionId」のマッピング経由で
パースする際に参照される。

JSON のキー命名は **Forms API レスポンス由来のものを camelCase 維持**
（``formId`` / ``responderUri`` / ``editUri``）、本ツール独自項目を snake_case と
する混合スタイル（``student_number_question_id`` / ``row_question_id_by_date`` /
``time_slot_labels``）。``populate_by_name=True`` で Python 側 snake_case 属性と
JSON 側 camelCase キーの双方を受け付ける。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FormInfo(BaseModel):
    """Google Form メタ情報。

    Phase 2.2 で ``app.services.google_forms.create_form()`` が生成し、
    ``<project_dir>/form.json`` に永続化する。
    Phase 2.3 のポーリング・パースで読み出される。
    """

    model_config = ConfigDict(
        extra="forbid",
        # JSON の "formId" でも Python の form_id でも受け取れるようにする
        populate_by_name=True,
    )

    form_id: str = Field(
        ..., alias="formId", description="Google Forms の Form ID"
    )
    responder_uri: str = Field(
        ...,
        alias="responderUri",
        description=(
            "回答者向け URL（``https://docs.google.com/forms/d/<id>/viewform``）"
        ),
    )
    edit_uri: str = Field(
        ...,
        alias="editUri",
        description=(
            "編集者向け URL。Forms API が直接返さないため、formId から構築する"
        ),
    )
    student_number_question_id: str = Field(
        ...,
        description="出席番号 TextQuestion の questionId（パース時に使用）",
    )
    comment_question_id: str | None = Field(
        default=None,
        description=(
            "自由記述コメント TextQuestion の questionId（任意項目）。"
            "Form 生成時に取得できなかった場合は None とし、"
            "回答パース時はコメント欄なしとして扱う"
        ),
    )
    row_question_id_by_date: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "候補日 (YYYY-MM-DD) → matrix 行 questionId のマッピング。"
            "Phase 2.3 の回答パースで availability を組み立てる際に使用"
        ),
    )
    time_slot_labels: list[str] = Field(
        default_factory=list,
        description=(
            "Form 生成時に使った時間枠ラベル (HH:MM-HH:MM) の順序付きリスト。"
            "回答パース時の整合性確認、および「終日」選択の展開に使用"
        ),
    )
    select_all_dates_row_question_id: str | None = Field(
        default=None,
        description=(
            "matrix 末尾に追加した「すべての日」行の questionId。"
            "この行でチェックされた時間枠は、回答パース時に全候補日へ展開される"
        ),
    )


__all__ = ["FormInfo"]
