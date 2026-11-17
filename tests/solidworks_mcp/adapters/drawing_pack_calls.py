"""One call of each drawing-pack adapter method, shared by the layer tests."""

from __future__ import annotations

from typing import Any

CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    (
        "create_section_view",
        ("Drawing View1", [10.0, 190.0], [130.0, 190.0], [250.0, 190.0]),
        {"label": "A"},
    ),
    (
        "create_detail_view",
        ("Drawing View1", [25.0, 155.0], 8.0, [300.0, 80.0]),
        {"scale": "3:1"},
    ),
    (
        "add_dimension",
        ("horizontal", [20.0, 160.0], [50.0, 240.0]),
        {"entity2_point": [80.0, 160.0]},
    ),
    ("auto_dimension_view", ("Drawing View1",), {"scheme": "chain"}),
    ("update_sheet_format", ("a2 - iso",), {"paper_size": "a2"}),
    ("update_title_block", ({"revision": "B"},), {}),
    ("drawing_report", (), {}),
]

IDS = [call[0] for call in CALLS]


def recorder() -> Any:
    """A mock adapter whose drawing-pack methods record their arguments."""
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
