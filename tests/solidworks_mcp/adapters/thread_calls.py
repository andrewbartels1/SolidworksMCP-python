"""One call of each adapter method queue item 43 adds, shared by the layer tests."""

from __future__ import annotations

from typing import Any

from solidworks_mcp.adapters.base import ThreadParameters

from .body_calls import recorder_for

CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    ("list_thread_sizes", ("metric",), {}),
    (
        "create_thread",
        (ThreadParameters(size="M6x1.0", edge_point=[3, 25, 0], length=12),),
        {},
    ),
]

IDS = [call[0] for call in CALLS]


def recorder() -> Any:
    """A mock adapter whose thread methods record their arguments."""
    return recorder_for(IDS)
