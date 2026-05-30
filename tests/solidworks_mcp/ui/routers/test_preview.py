"""Tests for preview router endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from solidworks_mcp.ui.routers import preview as preview_router


@pytest.mark.asyncio
async def test_preview_refresh_calls_service(monkeypatch) -> None:
    """preview_refresh should call refresh_preview."""
    # Patch the service call with an async mock.
    monkeypatch.setattr(preview_router, "refresh_preview", AsyncMock(return_value={"ok": True}))
    payload = preview_router.PreviewRefreshRequest(session_id="s1", orientation="front")
    result = await preview_router.preview_refresh(payload)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_feature_select_calls_service(monkeypatch) -> None:
    """feature_select should call highlight_feature."""
    # Patch the service call with an async mock.
    monkeypatch.setattr(preview_router, "highlight_feature", AsyncMock(return_value={"ok": True}))
    payload = preview_router.FeatureSelectRequest(session_id="s1", feature_name="Feat1")
    result = await preview_router.feature_select(payload)
    assert result == {"ok": True}
