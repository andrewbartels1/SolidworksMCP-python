"""One call of each sheet-metal adapter method, shared by the layer tests."""

from __future__ import annotations

from typing import Any

CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    ("create_base_flange", (2.0, 2.0), {"k_factor": 0.4, "sketch": "Sketch1"}),
    ("add_edge_flange", ([0.0, 0.0, 30.0], 20.0), {"angle": 45.0}),
    ("create_sketched_bend", (90.0,), {"reverse": True}),
    ("set_flat_pattern", (True,), {}),
]

IDS = [call[0] for call in CALLS]


def recorder() -> Any:
    """A mock adapter whose sheet-metal methods record their arguments."""
    from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
    from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

    def method(name: str) -> Any:
        async def call(self: Any, *args: Any, **kwargs: Any) -> AdapterResult[Any]:
            return AdapterResult(
                status=AdapterResultStatus.SUCCESS, data={name: [args, kwargs]}
            )

        return call

    body = {name: method(name) for name in IDS}
    return type("_Recorder", (MockSolidWorksAdapter,), body)({})
