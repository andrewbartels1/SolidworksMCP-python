"""Preview and feature-highlight routes for the Prefab CAD dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import DEFAULT_SESSION_ID, highlight_feature, refresh_preview

router = APIRouter()


class PreviewRefreshRequest(BaseModel):
    """Request payload for preview refresh requests."""

    session_id: str = DEFAULT_SESSION_ID
    orientation: str = "current"


class FeatureSelectRequest(BaseModel):
    """Request payload for highlighting a named feature in the SolidWorks model tree."""

    session_id: str = DEFAULT_SESSION_ID
    feature_name: str


@router.post("/api/ui/preview/refresh")
async def preview_refresh(payload: PreviewRefreshRequest) -> dict[str, Any]:
    """Export the current SolidWorks viewport to a PNG/GLB preview."""
    return await refresh_preview(payload.session_id, orientation=payload.orientation)


@router.post("/api/ui/feature/select")
async def feature_select(payload: FeatureSelectRequest) -> dict[str, Any]:
    """Select and highlight a named feature in the active SolidWorks model."""
    return await highlight_feature(payload.session_id, payload.feature_name)
