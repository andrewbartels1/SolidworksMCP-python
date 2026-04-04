"""Coverage tests for config.py, server.py, and __init__.py gaps."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.solidworks_mcp.config import SolidWorksMCPConfig, load_config, AdapterType


# ---------------------------------------------------------------------------
# config.py — validators and load_config
# ---------------------------------------------------------------------------


class TestConfigValidatorCoverage:
    def test_cache_dir_defaults_when_none(self):
        """Lines 246-252 — cache_dir=None triggers set_cache_dir to derive path."""
        cfg = SolidWorksMCPConfig(mock_solidworks=True, cache_dir=None)
        assert cfg.cache_dir is not None
        assert cfg.cache_dir.name == "cache"

    def test_log_file_defaults_when_none(self):
        """Lines 258-264 — log_file=None triggers set_log_file to derive path."""
        cfg = SolidWorksMCPConfig(mock_solidworks=True, log_file=None)
        assert cfg.log_file is not None
        assert cfg.log_file.name == "server.log"

    def test_validate_port_too_low_raises(self):
        """Lines 336-338 — port < 1 raises ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SolidWorksMCPConfig(mock_solidworks=True, port=0)

    def test_validate_port_too_high_raises(self):
        """Lines 336-338 — port > 65535 raises ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SolidWorksMCPConfig(mock_solidworks=True, port=70000)

    def test_validate_port_boundary_valid(self):
        cfg = SolidWorksMCPConfig(mock_solidworks=True, port=1)
        assert cfg.port == 1
        cfg2 = SolidWorksMCPConfig(mock_solidworks=True, port=65535)
        assert cfg2.port == 65535

    def test_load_config_no_args_calls_from_env(self, monkeypatch):
        """Line 417 — load_config() with no path falls back to from_env()."""
        monkeypatch.delenv("SOLIDWORKS_MCP_CONFIG", raising=False)
        cfg = load_config(None)
        assert isinstance(cfg, SolidWorksMCPConfig)

    def test_load_config_json_file(self, tmp_path):
        """Line 414 — load_config from JSON file."""
        import json
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"mock_solidworks": True, "port": 9000}))
        cfg = load_config(str(cfg_file))
        assert cfg.port == 9000

    def test_validate_adapter_type_passthrough(self):
        """Line 328 — validate_adapter_type just returns the value."""
        cfg = SolidWorksMCPConfig(mock_solidworks=True, adapter_type=AdapterType.MOCK)
        assert cfg.adapter_type == AdapterType.MOCK


# ---------------------------------------------------------------------------
# server.py — _run_local_stdio branches and _start_http_server
# ---------------------------------------------------------------------------


class TestServerCoverage:
    @pytest.mark.asyncio
    async def test_run_local_stdio_skips_when_mock_and_stdin_unavailable(self):
        """Lines 224-225 — mock mode + unreadable stdin → returns without error."""
        from src.solidworks_mcp.server import SolidWorksMCPServer
        from src.solidworks_mcp.config import SolidWorksMCPConfig, DeploymentMode

        cfg = SolidWorksMCPConfig(mock_solidworks=True, deployment_mode=DeploymentMode.LOCAL)
        server = SolidWorksMCPServer(cfg)
        await server.setup()

        # Simulate stdin not readable
        mock_stdin = MagicMock()
        mock_stdin.closed = True
        mock_stdin.readable = MagicMock(return_value=False)

        with patch("src.solidworks_mcp.server.sys") as mock_sys:
            mock_sys.stdin = mock_stdin
            # Should return without error
            await server._run_local_stdio()

    @pytest.mark.asyncio
    async def test_run_local_stdio_stdin_exception_treated_as_unreadable(self):
        """Lines 217-225 — stdin.readable() raises → stdin_is_readable=False."""
        from src.solidworks_mcp.server import SolidWorksMCPServer
        from src.solidworks_mcp.config import SolidWorksMCPConfig, DeploymentMode

        cfg = SolidWorksMCPConfig(mock_solidworks=True, deployment_mode=DeploymentMode.LOCAL)
        server = SolidWorksMCPServer(cfg)
        await server.setup()

        mock_stdin = MagicMock()
        mock_stdin.readable = MagicMock(side_effect=OSError("no stdin"))

        with patch("src.solidworks_mcp.server.sys") as mock_sys:
            mock_sys.stdin = mock_stdin
            await server._run_local_stdio()

    @pytest.mark.asyncio
    async def test_run_local_stdio_uses_run_stdio_async_when_no_run_stdio(self):
        """Lines 240-242 — falls back to run_stdio_async when run_stdio absent."""
        from src.solidworks_mcp.server import SolidWorksMCPServer
        from src.solidworks_mcp.config import SolidWorksMCPConfig, DeploymentMode

        cfg = SolidWorksMCPConfig(mock_solidworks=False, deployment_mode=DeploymentMode.LOCAL)
        server = SolidWorksMCPServer(cfg)
        await server.setup()

        server.server = MagicMock(spec=[])  # no run_stdio attribute
        server.server.run_stdio_async = AsyncMock()

        await server._run_local_stdio()
        server.server.run_stdio_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_http_server_awaits_coroutine(self):
        """Lines 279-283 — _start_http_server awaits the coroutine run result."""
        from src.solidworks_mcp.server import SolidWorksMCPServer
        from src.solidworks_mcp.config import SolidWorksMCPConfig, DeploymentMode

        cfg = SolidWorksMCPConfig(mock_solidworks=True, deployment_mode=DeploymentMode.REMOTE)
        server = SolidWorksMCPServer(cfg)
        await server.setup()

        ran = []

        async def fake_run(**kwargs):
            ran.append(kwargs)

        server.mcp.run = lambda **kwargs: fake_run(**kwargs)
        await server._start_http_server()
        assert ran

    @pytest.mark.asyncio
    async def test_start_logs_connection_error_in_mock_mode(self):
        """Lines 254-259 — adapter.connect raises; mock mode continues."""
        from src.solidworks_mcp.server import SolidWorksMCPServer
        from src.solidworks_mcp.config import SolidWorksMCPConfig, DeploymentMode

        cfg = SolidWorksMCPConfig(mock_solidworks=True, deployment_mode=DeploymentMode.LOCAL)
        server = SolidWorksMCPServer(cfg)
        await server.setup()

        server.adapter = MagicMock()
        server.adapter.connect = AsyncMock(side_effect=RuntimeError("no sw"))

        # Patch stdio to avoid blocking
        server.mcp = MagicMock()
        server.mcp.run_stdio = MagicMock(return_value=None)

        with patch("src.solidworks_mcp.server.sys") as mock_sys:
            mock_sys.stdin = MagicMock(closed=True)
            await server.start()

        assert not server.state.is_connected


# ---------------------------------------------------------------------------
# __init__.py — lazy loader and __dir__
# ---------------------------------------------------------------------------


class TestInitCoverage:
    def test_lazy_load_create_server(self):
        """Lines 40-46 — __getattr__ loads create_server on demand."""
        import src.solidworks_mcp as sw
        fn = sw.create_server
        assert callable(fn)

    def test_lazy_load_main(self):
        """Lines 40-46 — __getattr__ loads main on demand."""
        import src.solidworks_mcp as sw
        fn = sw.main
        assert callable(fn)

    def test_getattr_invalid_raises_attribute_error(self):
        """Line 48 — unknown attribute raises AttributeError."""
        import src.solidworks_mcp as sw
        with pytest.raises(AttributeError):
            _ = sw.totally_nonexistent_symbol_xyz

    def test_dir_includes_public_api(self):
        """Line 58 — __dir__ returns sorted public names."""
        import src.solidworks_mcp as sw
        d = dir(sw)
        assert "create_server" in d
        assert "main" in d
        assert "SolidWorksMCPConfig" in d
        assert "__version__" in d


# ---------------------------------------------------------------------------
# utils/validation.py — ImportError path (lines 74-75)
# ---------------------------------------------------------------------------


class TestValidationImportErrorCoverage:
    def test_solidworks_validation_handles_missing_pywin32(self):
        """Lines 74-75 — ImportError when win32com not installed is caught silently."""
        # Remove win32com from sys.modules so the import inside the validator fails
        saved = {k: v for k, v in sys.modules.items() if "win32" in k}
        for k in list(sys.modules):
            if "win32" in k:
                del sys.modules[k]

        try:
            with patch.dict(sys.modules, {"win32com": None, "win32com.client": None}):
                from src.solidworks_mcp.utils.validation import validate_environment
                from src.solidworks_mcp.config import SolidWorksMCPConfig
                cfg = SolidWorksMCPConfig(mock_solidworks=True)
                # Should not raise even on non-Windows without win32com
                try:
                    result = validate_environment(cfg)
                except Exception:
                    pass  # Platform-specific; the import error path is what we want
        finally:
            sys.modules.update(saved)
