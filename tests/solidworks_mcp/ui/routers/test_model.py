"""Tests for model router endpoints."""

from __future__ import annotations

import pytest

from solidworks_mcp.ui.routers import model as model_router


def test_connect_request_coerces_empty_uploads() -> None:
    """Empty upload payloads should coerce to None."""
    # Validate the field validator for uploaded_files.
    payload = model_router.ConnectTargetModelRequest(
        session_id="s1",
        model_path=None,
        uploaded_files="",
        feature_target_text=None,
    )
    assert payload.uploaded_files is None


@pytest.mark.asyncio
async def test_connect_model_calls_service(monkeypatch) -> None:
    """connect_model should call connect_target_model."""
    # Patch the service call to return a sentinel response.
    monkeypatch.setattr(model_router, "connect_target_model", lambda *_a, **_kw: {"ok": True})
    file_payload = model_router.UploadedFilePayload(
        name="part.sldprt",
        size=1,
        type="application/octet-stream",
        data="base64",
    )
    payload = model_router.ConnectTargetModelRequest(
        session_id="s1",
        model_path=None,
        uploaded_files=[file_payload],
        feature_target_text="Feat1",
    )
    result = await model_router.connect_model(payload)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_open_model_calls_service(monkeypatch) -> None:
    """open_model should call open_target_model."""
    # Patch the service call to return a sentinel response.
    monkeypatch.setattr(model_router, "open_target_model", lambda *_a, **_kw: {"ok": True})
    payload = model_router.OpenTargetModelRequest(
        session_id="s1",
        model_path="C:/tmp/model.sldprt",
        feature_target_text="Feat1",
    )
    result = await model_router.open_model(payload)
    assert result == {"ok": True}
