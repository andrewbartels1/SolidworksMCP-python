"""Drawing sheets on fake COM objects shaped like SolidWorks 2026's (queue item 37).

Spec: tools/drawing-sheets. The calls are the ones the probe of 2026-11-28
measured (design.md of the drawing-sheets change).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters import sw_type_info
from solidworks_mcp.adapters.base import (
    AdapterResult,
    AdapterResultStatus,
    AddSheetParameters,
)
from solidworks_mcp.adapters.solidworks import drawing_sheets

LETTER = (0.0, 13.0, 1.0, 1.0, 0.0, 0.2794, 0.2159, 1.0)


class _Drawing:
    """IDrawingDoc: sheets by name with their properties, one active."""

    def __init__(self, accept: bool = True) -> None:
        self.sheets: dict[str, tuple[float, ...]] = {"Sheet1": LETTER}
        self.active = "Sheet1"
        self.accept = accept
        self.added: tuple[Any, ...] = ()

    def GetSheetNames(self) -> tuple[str, ...]:
        return tuple(self.sheets)

    def _sheet(self, name: str) -> Any:
        return SimpleNamespace(
            GetName=lambda: name, GetProperties2=lambda: self.sheets[name]
        )

    def GetCurrentSheet(self) -> Any:
        return self._sheet(self.active)

    def Sheet(self, name: str) -> Any:
        return self._sheet(name)

    def NewSheet4(
        self,
        name: str,
        code: int,
        template: int,
        s1: float,
        s2: float,
        first: bool,
        path: str,
        width: float,
        height: float,
        *rest: Any,
    ) -> bool:
        self.added = (name, code, template, s1, s2, first, path, width, height, *rest)
        if self.accept:
            self.sheets[name] = (
                code,
                template,
                s1,
                s2,
                float(first),
                width,
                height,
                1.0,
            )
            self.active = name
        return self.accept

    def ActivateSheet(self, name: str) -> bool:
        if self.accept:
            self.active = name
        return self.accept


class _Harness(drawing_sheets.SolidWorksDrawingSheetsMixin):
    def __init__(self, drawing: Any) -> None:
        self.drawing = drawing

    def _attempt(self, operation: Any, default: Any = None) -> Any:
        try:
            return operation()
        except Exception:
            return default

    def _pack_drawing(self) -> Any:
        return self.drawing

    def _pack_format_path(self, sheet_format: str) -> str:
        return f"C:/formats/{sheet_format}.slddrt"

    def _pack_run(self, name: str, build: Any) -> AdapterResult[Any]:
        try:
            data = build()
        except Exception as e:  # mirrors PyWin32Adapter._handle_com_operation
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {e}"
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)


@pytest.fixture(autouse=True)
def plain_com(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sw_type_info, "flagged", lambda obj, *_: obj)


@pytest.mark.asyncio
async def test_list_sheets() -> None:
    result = await _Harness(_Drawing()).list_sheets()

    assert result.data == {
        "sheets": [
            {
                "name": "Sheet1",
                "active": True,
                "paper_mm": [279.4, 215.9],
                "scale": "1:1",
                "projection": "third",
            }
        ],
        "count": 1,
        "active": "Sheet1",
    }


@pytest.mark.asyncio
async def test_add_a_sheet_with_the_active_projection() -> None:
    drawing = _Drawing()

    result = await _Harness(drawing).add_sheet(
        AddSheetParameters(name=" Details ", scale="1:2")
    )

    assert result.data["added"] == "Details"
    assert result.data["active"] == "Details"
    name, code, template, s1, s2, first, path, width, height = drawing.added[:9]
    assert (name, code, template, s1, s2, first) == ("Details", 8, 12, 1.0, 2.0, False)
    assert path == "C:/formats/a3 - iso.slddrt"
    assert (width, height) == pytest.approx((0.42, 0.297))
    assert drawing.added[9:] == ("Default", 0, 0, 0, 0, 0, 0)


@pytest.mark.asyncio
async def test_a_given_projection() -> None:
    drawing = _Drawing()

    await _Harness(drawing).add_sheet(
        AddSheetParameters(name="D", sheet_format="a2 - iso", projection="first")
    )

    assert drawing.added[5] is True
    assert drawing.added[1] == 9


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "accept", "words"),
    [
        (AddSheetParameters(name="sheet1"), True, "already"),
        (AddSheetParameters(name="D", scale="big"), True, "scale 'big'"),
        (
            AddSheetParameters(name="D", sheet_format="letter"),
            True,
            "paper_size must be",
        ),
        (AddSheetParameters(name="D"), False, "SolidWorks added no sheet 'D'"),
    ],
)
async def test_refused_sheets(
    params: AddSheetParameters, accept: bool, words: str
) -> None:
    result = await _Harness(_Drawing(accept)).add_sheet(params)

    assert words in str(result.error)


@pytest.mark.asyncio
async def test_activate_a_sheet() -> None:
    drawing = _Drawing()
    drawing.sheets["Details"] = LETTER

    result = await _Harness(drawing).activate_sheet("DETAILS")

    assert result.data["active"] == "Details"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "accept", "words"),
    [("Nope", True, "No sheet named 'Nope'"), ("Sheet1", False, "did not activate")],
)
async def test_activate_failures(name: str, accept: bool, words: str) -> None:
    result = await _Harness(_Drawing(accept)).activate_sheet(name)

    assert words in str(result.error)
