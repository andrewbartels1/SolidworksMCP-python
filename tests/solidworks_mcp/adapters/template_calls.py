"""One call of each template adapter method, shared by the layer tests."""

from __future__ import annotations

from typing import Any

CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    ("get_template_folders", (), {}),
    ("save_as_template", ("C:/templates/Plate.prtdot",), {}),
]

IDS = [call[0] for call in CALLS]


def recorder() -> Any:
    """A mock adapter whose template methods record their arguments."""
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
