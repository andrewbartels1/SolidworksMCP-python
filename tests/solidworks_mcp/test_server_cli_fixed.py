"""Tests for the Typer CLI entrypoints in server_cli_fixed."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.solidworks_mcp import server_cli_fixed
from src.solidworks_mcp.config import DeploymentMode


class _FakeServer:
    """Minimal async server stub used by CLI tests."""

    start_calls = 0
    stop_calls = 0
    fail_with: BaseException | None = None

    def __init__(self, _config):
        """Test helper for init."""
        self.config = _config

    async def start(self) -> None:
        """Test helper for start."""
        type(self).start_calls += 1
        if type(self).fail_with is not None:
            raise type(self).fail_with

    async def stop(self) -> None:
        """Test helper for stop."""
        type(self).stop_calls += 1


def _make_config() -> SimpleNamespace:
    """Test helper for make config."""
    return SimpleNamespace(
        deployment_mode=DeploymentMode.LOCAL,
        host="localhost",
        port=8000,
        debug=False,
        log_level="INFO",
        mock_solidworks=False,
        security_level="minimal",
    )


def test_run_overrides_config_and_starts_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI run should apply overrides and execute start/stop lifecycle."""
    cfg = _make_config()
    _FakeServer.start_calls = 0
    _FakeServer.stop_calls = 0
    _FakeServer.fail_with = None

    monkeypatch.setattr(server_cli_fixed, "load_config", lambda _path: cfg)
    monkeypatch.setattr(server_cli_fixed.utils, "setup_logging", lambda _cfg: None)

    import src.solidworks_mcp.server as server_module

    monkeypatch.setattr(server_module, "SolidWorksMCPServer", _FakeServer)

    server_cli_fixed.run(
        config=None,
        mode="local",
        host="0.0.0.0",
        port=9001,
        debug=True,
        mock=True,
    )

    assert cfg.deployment_mode == DeploymentMode.LOCAL
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9001
    assert cfg.debug is True
    assert cfg.log_level == "DEBUG"
    assert cfg.mock_solidworks is True
    assert _FakeServer.start_calls == 1
    assert _FakeServer.stop_calls == 1


def test_run_handles_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI run should swallow KeyboardInterrupt and still stop server."""
    cfg = _make_config()
    _FakeServer.start_calls = 0
    _FakeServer.stop_calls = 0
    _FakeServer.fail_with = KeyboardInterrupt()

    monkeypatch.setattr(server_cli_fixed, "load_config", lambda _path: cfg)
    monkeypatch.setattr(server_cli_fixed.utils, "setup_logging", lambda _cfg: None)

    import src.solidworks_mcp.server as server_module

    monkeypatch.setattr(server_module, "SolidWorksMCPServer", _FakeServer)

    server_cli_fixed.run(
        config=None,
        mode=None,
        host="localhost",
        port=8000,
        debug=False,
        mock=False,
    )

    assert _FakeServer.start_calls == 1
    assert _FakeServer.stop_calls == 1


def test_run_reraises_unexpected_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI run should re-raise unexpected exceptions after cleanup."""
    cfg = _make_config()
    _FakeServer.start_calls = 0
    _FakeServer.stop_calls = 0
    _FakeServer.fail_with = RuntimeError("boom")

    monkeypatch.setattr(server_cli_fixed, "load_config", lambda _path: cfg)
    monkeypatch.setattr(server_cli_fixed.utils, "setup_logging", lambda _cfg: None)

    import src.solidworks_mcp.server as server_module

    monkeypatch.setattr(server_module, "SolidWorksMCPServer", _FakeServer)

    with pytest.raises(RuntimeError, match="boom"):
        server_cli_fixed.run(
            config=None,
            mode=None,
            host="localhost",
            port=8000,
            debug=False,
            mock=False,
        )

    assert _FakeServer.start_calls == 1
    assert _FakeServer.stop_calls == 1
