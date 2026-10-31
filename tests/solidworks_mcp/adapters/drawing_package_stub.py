"""A recording stub for the drawing-package adapter methods, shared by the
wrapper-adapter tests (circuit breaker and connection pool)."""

from __future__ import annotations

from typing import Any

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus

PACKAGE_ARGS = (
    "C:/parts/block.SLDPRT",
    "C:/out",
    "Block",
    "Test block",
    "BLK-01",
    "saiq",
    "B",
    "Acme",
    "25 Oct 2026",
    ["DEBURR"],
    False,
    False,
    3.0,
)


GTOL_ARGS = (
    "position",
    0.2,
    60.0,
    250.0,
    True,
    "mmc",
    ["A", "B"],
    (62.0, 218.0),
    ("Drawing View2", "D3@Sketch1"),
)


class DrawingPackageStub:
    """Records every drawing-package call and answers SUCCESS."""

    EXPECTED_CALLS = [
        (
            "insert_bom_table",
            ("Drawing View1", "bom.sldbomtbt", "indented", 10.0, 20.0),
        ),
        ("set_sheet_scale", (1.0, 2.0)),
        ("create_standard_drawing", PACKAGE_ARGS),
        ("add_gtol", GTOL_ARGS),
        ("add_datum_tag", ("A", (10.0, 20.0), 15.0, 25.0)),
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

    async def add_gtol(self, *args):
        return self._record("add_gtol", *args)

    async def add_datum_tag(self, *args):
        return self._record("add_datum_tag", *args)


async def exercise_drawing_package(wrapped: Any) -> None:
    """Call every drawing-package method once through ``wrapped``."""
    results = [
        await wrapped.insert_bom_table(
            "Drawing View1", "bom.sldbomtbt", "indented", 10.0, 20.0
        ),
        await wrapped.set_sheet_scale(1.0, 2.0),
        await wrapped.create_standard_drawing(*PACKAGE_ARGS),
        await wrapped.add_gtol(*GTOL_ARGS),
        await wrapped.add_datum_tag("A", (10.0, 20.0), 15.0, 25.0),
    ]
    assert all(r.is_success for r in results), [r.error for r in results]
