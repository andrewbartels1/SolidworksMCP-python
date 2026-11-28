"""One call of each adapter method queue item 37 adds, shared by the layer tests."""

from __future__ import annotations

from typing import Any

from solidworks_mcp.adapters.base import AddSheetParameters

from .body_calls import recorder_for

CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    ("list_sheets", (), {}),
    ("add_sheet", (AddSheetParameters(name="Details"),), {}),
    ("activate_sheet", ("Sheet1",), {}),
]

IDS = [call[0] for call in CALLS]


def recorder() -> Any:
    """A mock adapter whose sheet methods record their arguments."""
    return recorder_for(IDS)
