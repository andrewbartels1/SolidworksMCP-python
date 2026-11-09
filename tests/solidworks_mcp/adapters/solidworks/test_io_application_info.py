"""Tests for the pywin32 adapter's get_application_info (COM fakes)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter


def _build_adapter(monkeypatch) -> PyWin32Adapter:
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.platform.system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.pywintypes",
        SimpleNamespace(com_error=RuntimeError),
        raising=False,
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter._ComSessionCoordinator",
        lambda _adapter: SimpleNamespace(),
        raising=False,
    )
    return PyWin32Adapter({})


class _App:
    """ISldWorks answering the three reads, each of which can be made to fail."""

    def __init__(self, templates: dict[int, str], language: object = "english"):
        self.templates = templates
        self.language = language
        self.RevisionNumber = "34.4.0"

    def GetCurrentLanguage(self):  # noqa: N802
        if isinstance(self.language, Exception):
            raise self.language
        return self.language

    def GetUserPreferenceStringValue(self, preference):  # noqa: N802
        return self.templates.get(preference, "")


@pytest.mark.asyncio
async def test_reads_revision_language_and_template_names(
    monkeypatch, tmp_path: Path
) -> None:
    adapter = _build_adapter(monkeypatch)
    part = tmp_path / "Part.prtdot"
    part.write_text("")
    adapter.swApp = _App(
        {
            8: str(part),
            9: str(tmp_path / "missing.asmdot"),
        }
    )

    result = await adapter.get_application_info()

    assert result.is_success, result.error
    assert result.data == {
        "revision": "34.4.0",
        "language": "english",
        "templates": {
            "part": {"file_name": "Part.prtdot", "exists": True},
            "assembly": {"file_name": "missing.asmdot", "exists": False},
            "drawing": {"file_name": None, "exists": False},
        },
    }
    assert str(tmp_path) not in str(result.data)


@pytest.mark.asyncio
async def test_an_unreadable_value_is_none_and_the_rest_still_come_back(
    monkeypatch,
) -> None:
    adapter = _build_adapter(monkeypatch)
    adapter.swApp = _App({}, language=RuntimeError("Member not found"))

    result = await adapter.get_application_info()

    assert result.is_success, result.error
    assert result.data["language"] is None
    assert result.data["revision"] == "34.4.0"


@pytest.mark.asyncio
async def test_not_connected_is_an_error(monkeypatch) -> None:
    adapter = _build_adapter(monkeypatch)
    adapter.swApp = None

    result = await adapter.get_application_info()

    assert not result.is_success
    assert result.error == "Not connected to SolidWorks"
