"""Regression tests for preview model-binding behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.solidworks_mcp.ui.services import preview_service, session_service
from src.solidworks_mcp.ui.services._utils import merge_metadata


class _Result:
    """Minimal adapter result stub."""

    def __init__(self, *, is_success: bool = True, error: str | None = None):
        self.is_success = is_success
        self.error = error
        self.data = {}


@pytest.mark.asyncio
async def test_preview_does_not_export_when_reopen_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preview must fail fast instead of exporting from whichever document is active."""

    db_path = tmp_path / "ui.sqlite3"
    preview_dir = tmp_path / "previews"
    model_path = tmp_path / "candidate.sldprt"
    model_path.write_text("part", encoding="utf-8")

    session_service.ensure_dashboard_session("s-preview-reg", db_path=db_path)
    merge_metadata(
        "s-preview-reg",
        db_path=db_path,
        active_model_path=str(model_path),
    )

    class _Adapter:
        def __init__(self) -> None:
            self.export_attempted = False

        async def connect(self) -> None:
            return None

        async def disconnect(self) -> None:
            return None

        async def open_model(self, _path: str) -> _Result:
            return _Result(is_success=False, error="forced reopen failure")

        async def export_file(self, _out: str, _fmt: str) -> _Result:
            self.export_attempted = True
            return _Result(is_success=True)

        async def export_image(self, _payload: dict[str, Any]) -> _Result:
            self.export_attempted = True
            return _Result(is_success=True)

    adapter = _Adapter()

    monkeypatch.setattr(preview_service, "load_config", lambda: SimpleNamespace())

    async def _fake_create_adapter(_config: Any) -> Any:
        return adapter

    monkeypatch.setattr(preview_service, "create_adapter", _fake_create_adapter)

    state = await preview_service.refresh_preview(
        "s-preview-reg",
        db_path=db_path,
        preview_dir=preview_dir,
    )

    assert "Preview refresh failed" in state["latest_message"]
    assert "forced reopen failure" in state["latest_error_text"]
    assert adapter.export_attempted is False
