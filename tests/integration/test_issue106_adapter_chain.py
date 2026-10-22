"""Adapter-chain wiring for select_feature / select_face_edges / rebuild_model (#106).

Base defaults must return ERROR, and the circuit-breaker and connection-pool
wrappers must delegate every argument to the wrapped adapter.
"""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from tests.solidworks_mcp.adapters.test_base import _Adapter


class _RecordingAdapter:
    """Stub that records each call's arguments and returns SUCCESS."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    def _ok(self, name: str, *args: Any) -> AdapterResult[dict[str, Any]]:
        self.calls.append((name, args))
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data={"op": name})

    async def select_feature(self, feature_name, append=False):  # noqa: ANN001
        return self._ok("select_feature", feature_name, append)

    async def select_face_edges(  # noqa: ANN201
        self,
        point=None,
        side=None,
        plane=None,
        edge_type="all",
        append=False,  # noqa: ANN001
    ):
        return self._ok("select_face_edges", point, side, plane, edge_type, append)

    async def rebuild_model(self, top_level_only=False):  # noqa: ANN001
        return self._ok("rebuild_model", top_level_only)


async def _exercise(wrapped: Any) -> None:
    assert (await wrapped.select_feature("Boss-Extrude1", True)).is_success
    assert (
        await wrapped.select_face_edges(None, "top", None, "circular", True)
    ).is_success
    assert (await wrapped.rebuild_model(True)).is_success


_EXPECTED = [
    ("select_feature", ("Boss-Extrude1", True)),
    ("select_face_edges", (None, "top", None, "circular", True)),
    ("rebuild_model", (True,)),
]


@pytest.mark.asyncio
async def test_base_defaults_return_not_implemented_errors() -> None:
    """The base interface reports each new operation as not implemented."""
    adapter = _Adapter({})
    for result, name in [
        (await adapter.select_feature("F1"), "select_feature"),
        (await adapter.select_face_edges(side="top"), "select_face_edges"),
        (await adapter.rebuild_model(), "rebuild_model"),
    ]:
        assert result.status == AdapterResultStatus.ERROR
        assert name in (result.error or "")


@pytest.mark.asyncio
async def test_circuit_breaker_delegates_every_argument() -> None:
    """Circuit breaker passes calls and arguments straight through."""
    inner = _RecordingAdapter()
    await _exercise(CircuitBreakerAdapter(adapter=inner))
    assert inner.calls == _EXPECTED


@pytest.mark.asyncio
async def test_connection_pool_delegates_every_argument() -> None:
    """Connection pool passes calls and arguments straight through."""
    inner = _RecordingAdapter()
    pool = ConnectionPoolAdapter(adapter_factory=lambda: inner, max_size=1)
    await pool.connect()
    try:
        await _exercise(pool)
    finally:
        await pool.disconnect()
    assert inner.calls == _EXPECTED


class _AlwaysError:
    """Stub whose operations answer with an ERROR result (no exception)."""

    async def connect(self) -> None:
        return None

    async def rebuild_model(self, top_level_only=False):  # noqa: ANN001, ANN201
        return AdapterResult(status=AdapterResultStatus.ERROR, error="model has errors")

    async def select_feature(self, feature_name, append=False):  # noqa: ANN001, ANN201
        return AdapterResult(status=AdapterResultStatus.ERROR, error="not found")

    async def get_model_info(self):  # noqa: ANN201
        return AdapterResult(status=AdapterResultStatus.ERROR, error="broken")


@pytest.mark.asyncio
async def test_diagnostic_errors_do_not_trip_the_breaker() -> None:
    """Review #2: rebuild_model/select_feature ERROR answers never open the
    breaker (they are expected answers), while ordinary ops still do."""
    cb = CircuitBreakerAdapter(adapter=_AlwaysError(), failure_threshold=3)
    for _ in range(6):
        rebuild = await cb.rebuild_model()
        select = await cb.select_feature("Nope")
    assert rebuild.error == "model has errors"  # real answer, not "breaker open"
    assert select.error == "not found"
    for _ in range(3):
        await cb.get_model_info()
    tripped = await cb.get_model_info()
    assert "Circuit breaker is open" in (tripped.error or "")
