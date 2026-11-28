"""The mock adapter's drawing sheets (queue item 37).

The mock drawing starts with ``Sheet1`` (A3, 1:1, third angle). Adding a
sheet makes it active and sets the drawing pack's paper to its size, as the
real adapter's sheet does. Refusals use :mod:`sheet_rules`.
"""

from __future__ import annotations

from typing import Any

from ..exceptions import InputRefused
from . import sheet_rules as rules
from .base import AdapterResult, AdapterResultStatus, AddSheetParameters
from .solidworks.drawing_pack import PAPER_SIZES, paper_for, parse_scale


def _error(message: str) -> AdapterResult[dict[str, Any]]:
    """An error result."""
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


class MockDrawingSheetsMixin:
    """``list_sheets``, ``add_sheet`` and ``activate_sheet``, in memory."""

    def _sheets_state(self) -> dict[str, Any]:
        """The mock drawing's sheets and the active one."""
        state: dict[str, Any] = self._pack_state()  # type: ignore[attr-defined]
        if "sheets" not in state:
            state["sheets"] = [
                {
                    "name": "Sheet1",
                    "paper": state["paper"],
                    "scale": (1.0, 1.0),
                    "first": False,
                }
            ]
            state["active_sheet"] = "Sheet1"
        return state

    def _sheet_listing(self) -> dict[str, Any]:
        """Every sheet's entry, the active one marked."""
        state = self._sheets_state()
        sheets = []
        for sheet in state["sheets"]:
            _, width, height = PAPER_SIZES[sheet["paper"]]
            props = [
                0,
                12,
                *sheet["scale"],
                sheet["first"],
                width / 1000,
                height / 1000,
                1,
            ]
            sheets.append(
                rules.sheet_entry(
                    sheet["name"], props, sheet["name"] == state["active_sheet"]
                )
            )
        return {"sheets": sheets, "count": len(sheets), "active": state["active_sheet"]}

    def _guard(self, operation: str) -> AdapterResult[dict[str, Any]] | None:
        """An error unless a drawing is active."""
        guard: AdapterResult[dict[str, Any]] | None = self._pack_guard(operation)  # type: ignore[attr-defined]
        return guard

    async def list_sheets(self) -> AdapterResult[dict[str, Any]]:
        """Mock: the drawing's sheets."""
        refused = self._guard("list_sheets")
        if refused:
            return refused
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=self._sheet_listing()
        )

    async def add_sheet(
        self, params: AddSheetParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: add a sheet and make it active."""
        refused = self._guard("add_sheet")
        if refused:
            return refused
        state = self._sheets_state()
        try:
            rules.check_new_sheet(
                [s["name"] for s in state["sheets"]], params.name, params.projection
            )
            size = paper_for(params.sheet_format, params.paper_size)
            scale = parse_scale(params.scale)
        except (InputRefused, ValueError) as exc:
            return _error(str(exc))
        current = next(s for s in state["sheets"] if s["name"] == state["active_sheet"])
        first = (
            current["first"]
            if params.projection is None
            else params.projection == "first"
        )
        name = params.name.strip()
        state["sheets"].append(
            {"name": name, "paper": size, "scale": scale, "first": first}
        )
        state["active_sheet"] = name
        state["paper"] = size
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "added": name,
                "sheet_format": f"{params.sheet_format}.slddrt",
                **self._sheet_listing(),
            },
        )

    async def activate_sheet(self, name: str) -> AdapterResult[dict[str, Any]]:
        """Mock: make a sheet the active one."""
        refused = self._guard("activate_sheet")
        if refused:
            return refused
        state = self._sheets_state()
        try:
            real = rules.resolve_sheet([s["name"] for s in state["sheets"]], name)
        except InputRefused as exc:
            return _error(str(exc))
        state["active_sheet"] = real
        state["paper"] = next(s["paper"] for s in state["sheets"] if s["name"] == real)
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=self._sheet_listing()
        )
