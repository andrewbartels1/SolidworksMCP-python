"""A recording stub for the drawing-package adapter methods (BOM, sheet scale,
standard drawing), shared by the wrapper-adapter tests."""

from __future__ import annotations

from typing import Any

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus

_DRAWING_ARGS = (
    "C:/parts/block.SLDPRT",
    "C:/out",
    "Block",
    "Base",
    "BLK-01",
    "A. B.",
    "B",
    "ACME",
    "23 Oct 2026",
    ["Deburr"],
    False,
    False,
    3.0,
)


class DrawingPackageStub:
    """Records every drawing-package call and answers SUCCESS."""

    EXPECTED_CALLS = [
        ("insert_bom_table", ("Drawing View1", "t.sldbomtbt", "indented", 10.0, 20.0)),
        ("set_sheet_scale", (1, 2)),
        ("create_standard_drawing", _DRAWING_ARGS),
    ]

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def _record(self, name: str, *args: Any) -> AdapterResult[Any]:
        self.calls.append((name, args))
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=name)

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    def is_connected(self) -> bool:
        return True

    async def insert_bom_table(self, *args):
        return self._record("insert_bom_table", *args)

    async def set_sheet_scale(self, *args):
        return self._record("set_sheet_scale", *args)

    async def create_standard_drawing(self, *args):
        return self._record("create_standard_drawing", *args)


async def exercise_drawing_package(wrapped: Any) -> None:
    """Call every drawing-package method once through ``wrapped``."""
    results = [
        await wrapped.insert_bom_table(
            "Drawing View1", "t.sldbomtbt", "indented", 10.0, 20.0
        ),
        await wrapped.set_sheet_scale(1, 2),
        await wrapped.create_standard_drawing(*_DRAWING_ARGS),
    ]
    assert all(r.is_success for r in results), [r.error for r in results]
