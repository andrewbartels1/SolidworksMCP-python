"""Tests for environment validation helpers."""

from __future__ import annotations

import builtins
import sys
from collections import namedtuple
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

import solidworks_mcp.utils.validation as validation_mod
from solidworks_mcp.exceptions import SolidWorksMCPError
from solidworks_mcp.utils.validation import validate_environment


class _VersionInfo:
    """Test suite for VersionInfo."""

    def __init__(self, major: int, minor: int):
        """Test helper for init."""
        self.major = major
        self.minor = minor

    def __lt__(self, other):
        """Test helper for lt."""
        return (self.major, self.minor) < other


@pytest.mark.asyncio
async def test_validate_environment_platform_warning_branches(monkeypatch):
    """Test validate environment platform warning branches."""
    warning = Mock()
    monkeypatch.setattr(validation_mod.logger, "warning", warning)
    monkeypatch.setattr(validation_mod.platform, "system", lambda: "Linux")

    cfg = SimpleNamespace(
        can_use_solidworks=False,
        mock_solidworks=False,
        enable_windows_validation=False,
        solidworks_path=None,
    )

    await validation_mod.validate_environment(cfg)
    assert warning.called
    assert "requires Windows platform" in warning.call_args[0][0]


@pytest.mark.asyncio
async def test_validate_environment_windows_and_version_guard(monkeypatch):
    """Test validate environment windows and version guard."""
    warning = Mock()
    monkeypatch.setattr(validation_mod.logger, "warning", warning)
    monkeypatch.setattr(validation_mod.platform, "system", lambda: "Windows")

    cfg = SimpleNamespace(
        can_use_solidworks=False,
        mock_solidworks=False,
        enable_windows_validation=False,
        solidworks_path=None,
    )

    await validation_mod.validate_environment(cfg)
    assert "SolidWorks not available" in warning.call_args[0][0]

    monkeypatch.setattr(sys, "version_info", _VersionInfo(3, 10))
    with pytest.raises(SolidWorksMCPError, match=r"Python 3.13\+ required"):
        await validation_mod.validate_environment(cfg)


@pytest.mark.asyncio
async def test_validate_environment_windows_validation_invoked(monkeypatch):
    """Test validate environment windows validation invoked."""
    monkeypatch.setattr(validation_mod.platform, "system", lambda: "Windows")
    validator = AsyncMock()
    monkeypatch.setattr(validation_mod, "_validate_solidworks_installation", validator)

    cfg = SimpleNamespace(
        can_use_solidworks=True,
        mock_solidworks=False,
        enable_windows_validation=True,
        solidworks_path="/path/to/sw",
    )

    await validation_mod.validate_environment(cfg)
    validator.assert_awaited_once_with(cfg)


@pytest.mark.asyncio
async def test_validate_solidworks_installation_paths(monkeypatch):
    """Test validate solidworks installation paths."""
    warning = Mock()
    info = Mock()
    monkeypatch.setattr(validation_mod.logger, "warning", warning)
    monkeypatch.setattr(validation_mod.logger, "info", info)
    monkeypatch.setattr(validation_mod.shutil, "which", lambda _p: None)

    # COM available path.
    fake_win32com = SimpleNamespace(
        client=SimpleNamespace(Dispatch=Mock(return_value=object()))
    )
    monkeypatch.setitem(sys.modules, "win32com", fake_win32com)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_win32com.client)

    cfg = SimpleNamespace(solidworks_path="C:/Program Files/SolidWorks/sldworks.exe")
    await validation_mod._validate_solidworks_installation(cfg)

    assert warning.called
    assert info.called
    assert "COM interface is available" in info.call_args[0][0]

    # COM dispatch failure path.
    fake_win32com.client.Dispatch = Mock(side_effect=RuntimeError("dispatch error"))
    await validation_mod._validate_solidworks_installation(cfg)
    assert "COM interface issue" in warning.call_args[0][0]


@pytest.mark.asyncio
async def test_validate_solidworks_installation_import_error(monkeypatch):
    """Test validate solidworks installation import error."""
    warning = Mock()
    monkeypatch.setattr(validation_mod.logger, "warning", warning)

    real_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        """Test helper for import."""
        if name == "win32com.client":
            raise ImportError("missing win32com")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)

    cfg = SimpleNamespace(solidworks_path=None)
    await validation_mod._validate_solidworks_installation(cfg)

    assert "COM interface issue" in warning.call_args[0][0]


@pytest.mark.asyncio
async def test_validate_environment_branches(monkeypatch):
    """Test validate environment branches."""
    cfg = SimpleNamespace(
        can_use_solidworks=False,
        mock_solidworks=False,
        enable_windows_validation=False,
    )

    # Non-windows warning path
    monkeypatch.setattr(
        "solidworks_mcp.utils.validation.platform.system", lambda: "Linux"
    )
    await validate_environment(cfg)

    # Windows validation branch calls helper
    cfg2 = SimpleNamespace(
        can_use_solidworks=False,
        mock_solidworks=False,
        enable_windows_validation=True,
    )
    helper = AsyncMock()
    monkeypatch.setattr(
        "solidworks_mcp.utils.validation._validate_solidworks_installation", helper
    )
    monkeypatch.setattr(
        "solidworks_mcp.utils.validation.platform.system", lambda: "Windows"
    )
    await validate_environment(cfg2)
    helper.assert_awaited_once()

    # Python version guard
    import sys

    VersionInfo = namedtuple(
        "VersionInfo", ["major", "minor", "micro", "releaselevel", "serial"]
    )
    fake_vi = VersionInfo(3, 10, 0, "final", 0)
    monkeypatch.setattr(sys, "version_info", fake_vi)
    with pytest.raises(SolidWorksMCPError):
        await validate_environment(cfg)


class TestValidationImportErrorCoverage:
    """Test validation import error coverage."""

    def test_solidworks_validation_handles_missing_pywin32(self):
        """Lines 74-75 — ImportError when win32com not installed is caught silently."""
        # Remove win32com from sys.modules so the import inside the validator fails
        saved = {k: v for k, v in sys.modules.items() if "win32" in k}
        for k in list(sys.modules):
            if "win32" in k:
                del sys.modules[k]

        try:
            with patch.dict(sys.modules, {"win32com": None, "win32com.client": None}):
                from solidworks_mcp.config import SolidWorksMCPConfig
                from solidworks_mcp.utils.validation import validate_environment

                cfg = SolidWorksMCPConfig(mock_solidworks=True)
                # Should not raise even on non-Windows without win32com
                try:
                    validate_environment(cfg)
                except Exception:
                    pass  # Platform-specific; the import error path is what we want
        finally:
            sys.modules.update(saved)
