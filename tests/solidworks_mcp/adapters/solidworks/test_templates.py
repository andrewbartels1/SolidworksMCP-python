"""Saving the active document as a template, on fake COM objects.

Spec: tools/document-templates.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks.templates import (
    SolidWorksTemplatesMixin,
    in_folders,
    split_folders,
)


class _Harness(SolidWorksTemplatesMixin):
    """The mixin plus the PyWin32Adapter members it relies on."""

    def __init__(self, model: Any = None, folders: Any = "") -> None:
        self.currentModel = model
        self.swApp = SimpleNamespace(GetUserPreferenceStringValue=lambda _p: folders)

    def _handle_com_operation(self, name: str, operation: Any) -> AdapterResult[Any]:
        try:
            data = operation()
        except Exception as e:  # mirrors PyWin32Adapter._handle_com_operation
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {e}"
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)

    def _attempt(self, operation: Any, default: Any = None) -> Any:
        try:
            return operation()
        except Exception:
            return default

    def _get_attr_or_call(self, obj: Any, name: str) -> Any:
        value = getattr(obj, name)
        return value() if callable(value) else value


class _Part:
    """A part whose ``SaveAs3`` writes the file and can misbehave on request."""

    def __init__(self, kind: int = 1, code: Any = 0, moves: bool = False) -> None:
        self.kind, self.code, self.moves = kind, code, moves
        self.path = "C:/work/plate.SLDPRT"
        self.calls: list[tuple[Any, ...]] = []

    def GetType(self) -> int:
        return self.kind

    def GetPathName(self) -> str:
        return self.path

    def SaveAs3(self, path: str, version: int, options: int) -> Any:
        self.calls.append((path, version, options))
        if self.code == 0:
            Path(path).write_bytes(b"template")
        if self.moves:
            self.path = path
        return self.code


def test_split_folders() -> None:
    assert split_folders("C:/a; ;C:/b;") == ["C:/a", "C:/b"]
    assert split_folders(None) == []


def test_in_folders_compares_windows_paths() -> None:
    assert in_folders(r"C:\Templates\Plate.prtdot", ["c:/templates/"])
    assert not in_folders(r"C:\Other\Plate.prtdot", ["C:/Templates"])


@pytest.mark.asyncio
async def test_a_part_saves_a_copy_as_prtdot(tmp_path: Path) -> None:
    part = _Part()
    target = str(tmp_path / "Plate.prtdot")
    harness = _Harness(part, f"{tmp_path};C:/elsewhere")

    folders = await harness.get_template_folders()
    result = await harness.save_as_template(target)

    assert folders.data == {
        "folders": [str(tmp_path), "C:/elsewhere"],
        "document_type": "part",
        "extension": ".prtdot",
    }
    # Version 0 (current), options 3 (silent and copy).
    assert part.calls == [(target, 0, 3)]
    assert result.data == {
        "file_path": target,
        "document_type": "part",
        "in_template_folder": True,
        "template_folders": [str(tmp_path), "C:/elsewhere"],
        "document_path": "C:/work/plate.SLDPRT",
    }


@pytest.mark.asyncio
async def test_no_document_and_no_app() -> None:
    harness = _Harness()
    harness.swApp = None

    folders = await harness.get_template_folders()
    result = await harness.save_as_template("C:/t/x.prtdot")

    assert folders.data == {"folders": [], "document_type": None, "extension": None}
    assert result.error == "No active model"


@pytest.mark.asyncio
async def test_refusals_before_solidworks_is_asked(tmp_path: Path) -> None:
    unknown = _Part(kind=7)
    assembly = _Part(kind=2)

    odd = await _Harness(unknown).save_as_template(str(tmp_path / "x.prtdot"))
    wrong = await _Harness(assembly).save_as_template(str(tmp_path / "x.prtdot"))

    assert "needs an active part, assembly or drawing" in odd.error
    assert wrong.error.startswith("Assembly templates are .asmdot;")
    assert assembly.calls == []


@pytest.mark.asyncio
async def test_a_failed_save_and_a_switched_document(tmp_path: Path) -> None:
    failed = await _Harness(_Part(code=1)).save_as_template(str(tmp_path / "x.prtdot"))
    switched = await _Harness(_Part(moves=True)).save_as_template(
        str(tmp_path / "y.prtdot")
    )

    assert "didn't write the template" in failed.error
    assert "SaveAs3 returned 1" in failed.error
    assert "the open document is now" in switched.error
