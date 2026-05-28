"""Tests for the preview/feature highlight service."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.ui.services import preview_service


def _result(*, is_success: bool, error: str = "", data: dict | None = None) -> SimpleNamespace:
    """Build a simple adapter result."""
    return SimpleNamespace(is_success=is_success, error=error, data=data or {})


class _Adapter:
    """Configurable adapter stub for preview tests."""

    def __init__(
        self,
        *,
        export_file_cb=None,
        export_image_cb=None,
        select_feature_cb=None,
        open_model_cb=None,
        connect_cb=None,
    ) -> None:
        self.export_file_cb = export_file_cb
        self.export_image_cb = export_image_cb
        self.select_feature_cb = select_feature_cb
        self.open_model_cb = open_model_cb
        self.connect_cb = connect_cb

    async def connect(self) -> None:
        """Optionally raise during connect."""
        if self.connect_cb:
            self.connect_cb()

    async def disconnect(self) -> None:
        """No-op disconnect."""
        return None

    async def export_file(self, path: str, fmt: str):
        """Delegate export_file behavior."""
        if self.export_file_cb:
            return self.export_file_cb(path, fmt)
        return _result(is_success=False, error="no export_file handler")

    async def export_image(self, payload: dict):
        """Delegate export_image behavior."""
        if self.export_image_cb:
            return self.export_image_cb(payload)
        return _result(is_success=False, error="no export_image handler")

    async def select_feature(self, name: str):
        """Delegate select_feature behavior."""
        if self.select_feature_cb:
            return self.select_feature_cb(name)
        return _result(is_success=False, error="no select_feature handler")

    async def open_model(self, path: str):
        """Delegate open_model behavior."""
        if self.open_model_cb:
            return self.open_model_cb(path)
        return _result(is_success=True)


def test_public_preview_url_uses_mtime(tmp_path, monkeypatch) -> None:
    """Public preview URLs should include a cache-busting timestamp."""
    # Use a real file for the stat() branch, then a missing path for time.time.
    preview_file = tmp_path / "preview.png"
    preview_file.write_bytes(b"data")
    url = preview_service._public_preview_url(preview_file, api_origin="http://host")
    assert "http://host/previews/preview.png?ts=" in url

    monkeypatch.setattr(preview_service.time, "time", lambda: 123)
    missing = preview_service._public_preview_url(tmp_path / "missing.png", api_origin="http://host")
    assert missing.endswith("ts=123")


@pytest.mark.asyncio
async def test_reopen_target_model_raises_missing_path(tmp_path) -> None:
    """Reopen should fail fast when the target path is missing."""
    # Validate the missing-path guard in _reopen_target_model_for_preview.
    adapter = _Adapter()
    with pytest.raises(RuntimeError, match="does not exist"):
        await preview_service._reopen_target_model_for_preview(
            adapter,
            str(tmp_path / "missing.sldprt"),
            context="preview",
        )


@pytest.mark.asyncio
async def test_refresh_preview_missing_model_path(monkeypatch) -> None:
    """Missing active_model_path should surface as a refresh error."""
    # Force the early error branch when no active model is present.
    from solidworks_mcp.ui.services import session_service

    merge_calls: list[dict[str, object]] = []

    monkeypatch.setattr(session_service, "ensure_dashboard_session", lambda *_a, **_kw: None)
    monkeypatch.setattr(session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(preview_service, "get_design_session", lambda *_a, **_kw: {"metadata_json": "{}"})
    monkeypatch.setattr(preview_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw))
    monkeypatch.setattr(preview_service, "insert_tool_call_record", lambda **_kw: None)

    result = await preview_service.refresh_preview("s1", active_model_path_override=None)

    assert result == {"ok": True}
    assert any("Preview refresh failed" in call.get("preview_status", "") for call in merge_calls)


@pytest.mark.asyncio
async def test_refresh_preview_stl_fallback_and_png_failure(monkeypatch, tmp_path) -> None:
    """STL fallback and PNG failure paths should update metadata."""
    # Exercise GLB fail -> STL success and PNG failure branches.
    from solidworks_mcp.ui.services import session_service

    def export_file(path: str, fmt: str):
        if fmt == "stl":
            Path(path).write_bytes(b"stl")
            return _result(is_success=True)
        return _result(is_success=False, error="glb failed")

    def export_image(_payload: dict):
        return _result(is_success=False, error="png failed")

    adapter_main = _Adapter(export_file_cb=export_file, export_image_cb=export_image)

    def _views_connect_fail():
        raise RuntimeError("views connect fail")

    adapter_views = _Adapter(connect_cb=_views_connect_fail)
    adapters = [adapter_main, adapter_views]

    async def _create_adapter(_cfg):
        return adapters.pop(0)

    merge_calls: list[dict[str, object]] = []
    metadata = {"active_model_path": "C:/tmp/model.sldprt", "preview_view_urls": {"front": "old"}}

    monkeypatch.setattr(preview_service, "create_adapter", _create_adapter)
    monkeypatch.setattr(preview_service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(session_service, "ensure_dashboard_session", lambda *_a, **_kw: None)
    monkeypatch.setattr(session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(preview_service, "get_design_session", lambda *_a, **_kw: {"metadata_json": json.dumps(metadata)})
    monkeypatch.setattr(preview_service, "insert_model_state_snapshot", lambda **_kw: 1)
    monkeypatch.setattr(preview_service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(preview_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw))
    monkeypatch.setattr(preview_service, "ensure_preview_dir", lambda _p=None: tmp_path)

    result = await preview_service.refresh_preview(
        "s1",
        preview_dir=tmp_path,
        active_model_path_override="C:/tmp/model.sldprt",
        reopen_active_model=False,
    )

    assert result == {"ok": True}
    assert any("fmt=stl" in call.get("preview_viewer_url", "") for call in merge_calls)
    assert any(call.get("preview_png_ready") is False for call in merge_calls)
    assert any(call.get("preview_view_urls") == {"front": "old"} for call in merge_calls)


@pytest.mark.asyncio
async def test_refresh_preview_merges_view_urls_with_new_images(monkeypatch, tmp_path) -> None:
    """View URL merges should preserve existing entries and add new ones."""
    # Cover re-select error handling and per-view export outcomes.
    from solidworks_mcp.ui.services import session_service

    def export_file(path: str, fmt: str):
        Path(path).write_bytes(b"glb")
        return _result(is_success=True)

    def export_image_main(_payload: dict):
        return _result(is_success=True)

    adapter_main = _Adapter(export_file_cb=export_file, export_image_cb=export_image_main)

    select_calls = {"count": 0}

    def select_feature(name: str):
        select_calls["count"] += 1
        if select_calls["count"] == 1:
            raise RuntimeError("select failed")
        return _result(is_success=True)

    def export_image_views(payload: dict):
        view = payload.get("view_orientation")
        view_path = Path(payload["file_path"])
        if view == "front":
            view_path.write_bytes(b"front")
            return _result(is_success=True)
        if view == "top":
            return _result(is_success=False, error="failed")
        raise RuntimeError("boom")

    adapter_views = _Adapter(
        export_image_cb=export_image_views,
        select_feature_cb=select_feature,
    )
    adapters = [adapter_main, adapter_views]

    async def _create_adapter(_cfg):
        return adapters.pop(0)

    merge_calls: list[dict[str, object]] = []
    metadata = {
        "active_model_path": "C:/tmp/model.sldprt",
        "preview_view_urls": {"front": "old", "right": "old-right"},
        "selected_feature_name": "Feat1",
    }

    monkeypatch.setattr(preview_service, "create_adapter", _create_adapter)
    monkeypatch.setattr(preview_service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(session_service, "ensure_dashboard_session", lambda *_a, **_kw: None)
    monkeypatch.setattr(session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(preview_service, "get_design_session", lambda *_a, **_kw: {"metadata_json": json.dumps(metadata)})
    monkeypatch.setattr(preview_service, "insert_model_state_snapshot", lambda **_kw: 1)
    monkeypatch.setattr(preview_service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(preview_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw))
    monkeypatch.setattr(preview_service, "ensure_preview_dir", lambda _p=None: tmp_path)

    result = await preview_service.refresh_preview(
        "s1",
        preview_dir=tmp_path,
        active_model_path_override="C:/tmp/model.sldprt",
        reopen_active_model=False,
    )

    assert result == {"ok": True}
    merged = next(call.get("preview_view_urls") for call in merge_calls if "preview_view_urls" in call)
    assert merged["front"] != "old"
    assert merged["right"] == "old-right"


@pytest.mark.asyncio
async def test_highlight_feature_parses_snapshots_and_selects(monkeypatch, tmp_path) -> None:
    """Highlight should parse feature trees and select features."""
    # Cover feature-tree parsing and selection success branches.
    from solidworks_mcp.ui.services import session_service

    active_model = tmp_path / "model.sldprt"
    active_model.write_bytes(b"model")

    def select_feature(_name: str):
        return _result(is_success=True, data={"selected": True, "entity_type": "Face", "selected_name": "Feat1"})

    adapter = _Adapter(select_feature_cb=select_feature)

    async def _create_adapter(_cfg):
        return adapter

    merge_calls: list[dict[str, object]] = []
    snapshots = [
        {"feature_tree_json": ""},
        {"feature_tree_json": "{bad json"},
        {"feature_tree_json": json.dumps([{"name": "Feat1"}])},
    ]

    monkeypatch.setattr(preview_service, "create_adapter", _create_adapter)
    monkeypatch.setattr(preview_service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(session_service, "ensure_dashboard_session", lambda *_a, **_kw: None)
    monkeypatch.setattr(session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(
        preview_service,
        "get_design_session",
        lambda *_a, **_kw: {"metadata_json": json.dumps({"active_model_path": str(active_model)})},
    )
    monkeypatch.setattr(preview_service, "list_model_state_snapshots", lambda *_a, **_kw: snapshots)
    monkeypatch.setattr(preview_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw))
    monkeypatch.setattr(preview_service, "insert_tool_call_record", lambda **_kw: None)

    result = await preview_service.highlight_feature("s1", "Feat1")

    assert result == {"ok": True}
    assert any(call.get("selected_feature_name") == "Feat1" for call in merge_calls)


@pytest.mark.asyncio
async def test_highlight_feature_handles_exception(monkeypatch) -> None:
    """Exceptions in highlight_feature should be captured in metadata."""
    # Force connect to raise and validate the exception handler.
    from solidworks_mcp.ui.services import session_service

    def _connect_fail():
        raise RuntimeError("boom")

    adapter = _Adapter(connect_cb=_connect_fail)

    async def _create_adapter(_cfg):
        return adapter

    merge_calls: list[dict[str, object]] = []

    monkeypatch.setattr(preview_service, "create_adapter", _create_adapter)
    monkeypatch.setattr(preview_service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(session_service, "ensure_dashboard_session", lambda *_a, **_kw: None)
    monkeypatch.setattr(session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(preview_service, "get_design_session", lambda *_a, **_kw: {"metadata_json": "{}"})
    monkeypatch.setattr(preview_service, "list_model_state_snapshots", lambda *_a, **_kw: [])
    monkeypatch.setattr(preview_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw))

    result = await preview_service.highlight_feature("s1", "Feat1")

    assert result == {"ok": True}
    assert any(call.get("latest_error_text") == "boom" for call in merge_calls)
