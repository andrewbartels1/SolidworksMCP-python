"""A recording stub for the drawing-dimension adapter methods, shared by the
wrapper-adapter tests (circuit breaker and connection pool)."""

from __future__ import annotations

from typing import Any

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus


class DrawingDimensionsStub:
    """Records every drawing-dimension call and answers SUCCESS."""

    EXPECTED_CALLS = [
        ("insert_model_dimensions", ("Drawing View1", False)),
        ("arrange_dimensions", ("Drawing View1",)),
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

    async def insert_model_dimensions(self, view_name=None, include_hole_wizard=True):
        return self._record("insert_model_dimensions", view_name, include_hole_wizard)

    async def arrange_dimensions(self, view_name=None):
        return self._record("arrange_dimensions", view_name)


async def exercise_drawing_dimensions(wrapped: Any) -> None:
    """Call every drawing-dimension method once through ``wrapped``."""
    results = [
        await wrapped.insert_model_dimensions("Drawing View1", False),
        await wrapped.arrange_dimensions("Drawing View1"),
    ]
    assert all(r.is_success for r in results), [r.error for r in results]
