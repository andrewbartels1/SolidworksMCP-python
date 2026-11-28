"""Drawing sheets on SolidWorks (queue item 37): list, add and activate.

Measured on SolidWorks 2026 (design.md of the ``drawing-sheets`` change):
``IDrawingDoc.GetSheetNames`` lists them; ``IDrawingDoc.Sheet(name)`` gives
one without activating it; ``NewSheet4`` with a custom format (template 12,
the paper size code and size in metres, as ``SetupSheet5`` takes them) adds
one and makes it active, and returns False for a name in use;
``ActivateSheet`` returns False for a missing name.

Every call runs on the connect thread through the drawing pack's
``_pack_run``, which refuses anything but a drawing.
"""

from __future__ import annotations

from typing import Any, cast

from ...exceptions import InputRefused
from .. import sheet_rules as rules
from .. import sw_type_info
from ..base import AdapterResult, AddSheetParameters
from .com_utils import as_list
from .drawing_pack import PAPER_SIZES, TEMPLATE_CUSTOM, paper_for, parse_scale


class SolidWorksDrawingSheetsMixin:
    """``list_sheets``, ``add_sheet`` and ``activate_sheet``."""

    def _sheet_names(self, drawing: Any) -> list[str]:
        """The drawing's sheet names, in order."""
        adapter: Any = self
        return [
            str(n) for n in as_list(adapter._attempt(lambda: drawing.GetSheetNames()))
        ]

    def _active_sheet(self, drawing: Any) -> str:
        """The active sheet's name."""
        adapter: Any = self
        sheet = sw_type_info.flagged(
            adapter._attempt(lambda: drawing.GetCurrentSheet()), "ISheet"
        )
        return str(adapter._attempt(lambda: sheet.GetName(), default=""))

    def _sheet_listing(self, drawing: Any) -> dict[str, Any]:
        """Every sheet's entry, the active one marked, read without switching."""
        adapter: Any = self
        active = self._active_sheet(drawing)
        sheets = []
        for name in self._sheet_names(drawing):
            sheet = sw_type_info.flagged(
                adapter._attempt(lambda n=name: drawing.Sheet(n)), "ISheet"
            )
            props = adapter._attempt(lambda s=sheet: s.GetProperties2())
            sheets.append(rules.sheet_entry(name, props, name == active))
        return {"sheets": sheets, "count": len(sheets), "active": active}

    async def list_sheets(self) -> AdapterResult[dict[str, Any]]:
        """The active drawing's sheets.

        Returns:
            AdapterResult[dict[str, Any]]: ``sheets`` (see
            :func:`..sheet_rules.sheet_entry`), ``count`` and ``active``.
        """
        adapter: Any = self
        return cast(
            AdapterResult[dict[str, Any]],
            adapter._pack_run(
                "list_sheets", lambda: self._sheet_listing(adapter._pack_drawing())
            ),
        )

    async def add_sheet(
        self, params: AddSheetParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Add a sheet and make it active.

        Args:
            params: The name, format, paper, scale and projection.

        Returns:
            AdapterResult[dict[str, Any]]: ``added``, ``sheet_format`` and the
            listing after.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            drawing = adapter._pack_drawing()
            rules.check_new_sheet(
                self._sheet_names(drawing), params.name, params.projection
            )
            try:
                size = paper_for(params.sheet_format, params.paper_size)
                scale = parse_scale(params.scale)
            except ValueError as exc:
                raise InputRefused(str(exc)) from exc
            path = adapter._pack_format_path(params.sheet_format)
            if params.projection is None:
                current = sw_type_info.flagged(drawing.GetCurrentSheet(), "ISheet")
                props = as_list(adapter._attempt(lambda: current.GetProperties2()))
                first_angle = bool(props[4]) if len(props) >= 5 else False
            else:
                first_angle = params.projection == "first"
            code, width, height = PAPER_SIZES[size]
            made = drawing.NewSheet4(
                params.name.strip(),
                code,
                TEMPLATE_CUSTOM,
                scale[0],
                scale[1],
                first_angle,
                path,
                width / 1000.0,
                height / 1000.0,
                "Default",
                0,
                0,
                0,
                0,
                0,
                0,
            )
            if not made:
                raise RuntimeError(f"SolidWorks added no sheet '{params.name}'.")
            return {
                "added": params.name.strip(),
                "sheet_format": path,
                **self._sheet_listing(drawing),
            }

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._pack_run("add_sheet", build),
        )

    async def activate_sheet(self, name: str) -> AdapterResult[dict[str, Any]]:
        """Make a sheet the active one.

        Args:
            name: The sheet, ignoring case.

        Returns:
            AdapterResult[dict[str, Any]]: The listing after.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            drawing = adapter._pack_drawing()
            real = rules.resolve_sheet(self._sheet_names(drawing), name)
            if not drawing.ActivateSheet(real):
                raise RuntimeError(f"SolidWorks did not activate sheet '{real}'.")
            return self._sheet_listing(drawing)

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._pack_run("activate_sheet", build),
        )
