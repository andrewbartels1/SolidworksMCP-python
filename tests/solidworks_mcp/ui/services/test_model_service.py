"""Tests for model connection helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.ui.services import model_service


class _Adapter:
    """Adapter stub for model service tests."""

    def __init__(self, *, disconnect_raises: bool = False) -> None:
        self.disconnect_raises = disconnect_raises

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        if self.disconnect_raises:
            raise RuntimeError("disconnect failed")

    async def open_model(self, _path: str):
        return SimpleNamespace(is_success=True, error="")

    async def get_model_info(self):
        return SimpleNamespace(is_success=True, data={"type": "Part", "configuration": "Default"})

    async def list_features(self, include_suppressed: bool = True):
        return SimpleNamespace(is_success=True, data=[{"name": "Feat1"}])


def test_resolve_model_path_upload_error(monkeypatch) -> None:
    """Upload errors should be captured and return None."""
    # Force materialize_uploaded_model to raise and assert merge_metadata updates.
    merge_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        model_service,
        "materialize_uploaded_model",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("bad upload")),
    )
    monkeypatch.setattr(model_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw))

    result = model_service._resolve_model_path(
        "s1",
        model_path=None,
        uploaded_files=[{"name": "part.sldprt"}],
        feature_target_text="",
        db_path=None,
        api_origin="http://localhost",
    )

    assert result is None
    assert any("Uploaded model could not be prepared" in call.get("latest_message", "") for call in merge_calls)


@pytest.mark.asyncio
async def test_open_target_model_disconnect_failure(monkeypatch, tmp_path) -> None:
    """Disconnect failures should be handled during open_target_model."""
    # Ensure disconnect exception path is exercised.
    from solidworks_mcp.ui.services import session_service

    model_path = tmp_path / "model.sldprt"
    model_path.write_bytes(b"model")

    adapter = _Adapter(disconnect_raises=True)

    async def _create_adapter(_cfg):
        return adapter

    monkeypatch.setattr(model_service, "create_adapter", _create_adapter)
    monkeypatch.setattr(model_service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(session_service, "ensure_dashboard_session", lambda *_a, **_kw: None)
    monkeypatch.setattr(session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(model_service, "merge_metadata", lambda *_a, **_kw: {})
    monkeypatch.setattr(model_service, "insert_tool_call_record", lambda **_kw: None)

    result = await model_service.open_target_model("s1", model_path=str(model_path))

    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_connect_target_model_refresh_preview_failure(monkeypatch, tmp_path) -> None:
    """refresh_preview failures should log and continue cleanup."""
    # Force refresh_preview to raise and ensure cleanup proceeds.
    from solidworks_mcp.ui.services import session_service

    model_path = tmp_path / "model.sldprt"
    model_path.write_bytes(b"model")

    adapter = _Adapter(disconnect_raises=True)

    async def _create_adapter(_cfg):
        return adapter

    async def _refresh_preview(*_a, **_kw):
        raise RuntimeError("preview fail")

    monkeypatch.setattr(model_service, "create_adapter", _create_adapter)
    monkeypatch.setattr(model_service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(model_service, "classify_feature_tree_snapshot", lambda *_a, **_kw: {"family": "extrude", "confidence": "high", "evidence": [], "warnings": []})
    monkeypatch.setattr(model_service, "insert_model_state_snapshot", lambda **_kw: 1)
    monkeypatch.setattr(model_service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(model_service, "insert_evidence_link", lambda **_kw: None)
    monkeypatch.setattr(model_service, "merge_metadata", lambda *_a, **_kw: {})
    monkeypatch.setattr(model_service, "ensure_preview_dir", lambda _p=None: tmp_path)
    from solidworks_mcp.ui.services import preview_service

    monkeypatch.setattr(preview_service, "refresh_preview", _refresh_preview)

    monkeypatch.setattr(session_service, "ensure_dashboard_session", lambda *_a, **_kw: None)
    monkeypatch.setattr(session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True})

    result = await model_service.connect_target_model("s1", model_path=str(model_path))

    assert result == {"ok": True}
