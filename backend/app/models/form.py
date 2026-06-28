"""Google Form メタ情報モデル。

requirements.md §3.1 のディレクトリ構成で ``form.json`` として永続化される情報を表す。
詳細スキーマは Phase 2.0（Forms API 仕様調査）/ Phase 2.2（Form 作成実装）で確定するため、
本フェーズでは最低限のフィールドのみ定義し、後続フェーズで拡張する。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FormInfo(BaseModel):
    """Google Form のメタ情報（``form.json`` 直列化用）。"""

    model_config = ConfigDict(extra="allow")

    project_id: str = Field(..., description="所属プロジェクトID")
    form_id: str = Field(..., description="Google Forms の formId")
    responder_uri: str = Field(..., description="生徒が回答に使う URL")
    edit_uri: str | None = Field(None, description="編集用 URL（取得可能な場合）")
    created_at: datetime = Field(..., description="作成日時（TZ 付き）")
