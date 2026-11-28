"""One call of each adapter method queue item 35 adds, shared by the layer tests."""

from __future__ import annotations

from typing import Any

from solidworks_mcp.adapters.base import (
    CombineBodiesParameters,
    DeleteBodiesParameters,
    MoveCopyBodyParameters,
    ScaleBodyParameters,
    SplitBodyParameters,
)

CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    ("list_bodies", (), {}),
    (
        "combine_bodies",
        (
            CombineBodiesParameters(
                operation="subtract", main_body="Block", tool_bodies=["Pin"]
            ),
        ),
        {},
    ),
    ("split_body", (SplitBodyParameters(tool="Right Plane"),), {}),
    (
        "move_copy_body",
        (MoveCopyBodyParameters(bodies=["Block"], translate=[1, 0, 0]),),
        {},
    ),
    ("delete_bodies", (DeleteBodiesParameters(bodies=["Pin"]),), {}),
    ("scale_body", (ScaleBodyParameters(scale=2),), {}),
]

IDS = [call[0] for call in CALLS]


def recorder() -> Any:
    """A mock adapter whose body methods record their arguments."""
    return recorder_for(IDS)


def recorder_for(names: list[str]) -> Any:
    """A mock adapter whose methods ``names`` record their arguments."""
    from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
    from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

    def method(name: str) -> Any:
        async def call(self: Any, *args: Any, **kwargs: Any) -> AdapterResult[Any]:
            return AdapterResult(
                status=AdapterResultStatus.SUCCESS, data={name: [args, kwargs]}
            )

        return call

    body = {name: method(name) for name in names}
    return type("_Recorder", (MockSolidWorksAdapter,), body)({})
