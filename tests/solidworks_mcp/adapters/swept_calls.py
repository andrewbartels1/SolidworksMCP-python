"""One call of each adapter method queue item 34 adds, shared by the layer tests."""

from __future__ import annotations

from typing import Any

from solidworks_mcp.adapters.base import HelixParameters, SweepParameters

CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    ("create_helix", (HelixParameters(sketch="Sketch1", height=48, pitch=6),), {}),
    ("create_cut_sweep", (SweepParameters(path="Helix/Spiral1"),), {}),
]

IDS = [call[0] for call in CALLS]


def recorder() -> Any:
    """A mock adapter whose helix and cut-sweep methods record their arguments."""
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
