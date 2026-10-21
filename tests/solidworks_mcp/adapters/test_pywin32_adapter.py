"""Tests for solidworks_mcp.adapters.pywin32_adapter module-level behaviour."""

from __future__ import annotations


def test_pywin32_adapter_imports_without_pywin32(import_without) -> None:
    """Non-Windows CI: the module imports and reports pywin32 as unavailable."""
    attrs = import_without(
        "solidworks_mcp.adapters.pywin32_adapter",
        [
            "pythoncom",
            "pywintypes",
            "win32com",
            "win32com.client",
            "win32com.client.dynamic",
        ],
        ["PYWIN32_AVAILABLE", "pywintypes"],
    )

    assert attrs["PYWIN32_AVAILABLE"] is False
    assert "com_error" in attrs["pywintypes"]
