"""Model open/connect routes for the Prefab CAD dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from ..services import (
    DEFAULT_SESSION_ID,
    connect_target_model,
    open_target_model,
)

router = APIRouter()


class UploadedFilePayload(BaseModel):
    """Browser-uploaded file payload returned by Prefab's OpenFilePicker action."""

    name: str
    size: int
    type: str
    data: str


class ConnectTargetModelRequest(BaseModel):
    """Request payload for attaching an active SolidWorks target model."""

    session_id: str = DEFAULT_SESSION_ID
    model_path: str | None = None
    uploaded_files: list[UploadedFilePayload] | None = None
    feature_target_text: str | None = None

    @field_validator("uploaded_files", mode="before")
    @classmethod
    def _coerce_empty_uploaded_files(cls, v: object) -> object:
        """Coerce empty string or empty list to None so Pydantic accepts it."""
        if v == "" or v == []:
            return None
        return v


class OpenTargetModelRequest(BaseModel):
    """Request payload for opening a target model by file path."""

    session_id: str = DEFAULT_SESSION_ID
    model_path: str | None = None
    feature_target_text: str | None = None


@router.post("/api/ui/model/connect")
async def connect_model(payload: ConnectTargetModelRequest) -> dict[str, Any]:
    """Attach a target SolidWorks document and derive grounded feature-tree context."""
    return await connect_target_model(
        payload.session_id,
        model_path=payload.model_path,
        uploaded_files=(
            [f.model_dump() for f in payload.uploaded_files]
            if payload.uploaded_files
            else None
        ),
        feature_target_text=payload.feature_target_text,
    )


@router.post("/api/ui/model/open")
async def open_model(payload: OpenTargetModelRequest) -> dict[str, Any]:
    """Open a SolidWorks model by path and reflect its feature tree into the session."""
    return await open_target_model(
        payload.session_id,
        model_path=payload.model_path,
        feature_target_text=payload.feature_target_text,
    )
