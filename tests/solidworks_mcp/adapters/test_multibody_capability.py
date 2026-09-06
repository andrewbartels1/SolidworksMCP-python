"""Contract + mock-behaviour tests for the multibody capability.

``save_body_as_part`` exists on the base adapter, the mock, the circuit
breaker and the connection pool. A method missing from either wrapper
silently degrades to the base "not implemented" default at runtime, and mock
mode cannot catch it — the mock is not wrapped — so the wiring is asserted
directly here.

Implemented on ``SolidWorksIOMixin`` in
``src/solidworks_mcp/adapters/solidworks/io.py``
(``_save_body`` via ``IFeatureManager::CreateSaveBodyFeature``).
"""

import inspect
import os

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

WRAPPERS = [
    SolidWorksAdapter,
    MockSolidWorksAdapter,
    CircuitBreakerAdapter,
    ConnectionPoolAdapter,
]


@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_save_body_as_part_exists_on_every_layer(cls: type) -> None:
    """Every adapter layer defines ``save_body_as_part`` as an async method."""
    method = getattr(cls, "save_body_as_part", None)
    assert method is not None, f"{cls.__name__} is missing save_body_as_part"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.save_body_as_part must be async"
    )


def test_wrappers_do_not_silently_fall_through_to_base() -> None:
    """The breaker and pool define their own pass-through, not inherit the stub."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert "save_body_as_part" in vars(cls), (
            f"{cls.__name__} inherits save_body_as_part from the base adapter"
        )


def test_real_adapter_resolves_to_the_io_mixin() -> None:
    """PyWin32Adapter resolves ``save_body_as_part`` to the COM mixin, not the stub."""
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (
            k.__name__
            for k in PyWin32Adapter.__mro__
            if "save_body_as_part" in vars(k)
        ),
        None,
    )
    assert owner == "SolidWorksIOMixin", (
        f"PyWin32Adapter.save_body_as_part resolves to {owner}, not the COM mixin."
    )


@pytest.mark.asyncio
async def test_base_default_reports_missing_capability() -> None:
    """The base default returns an error naming the missing capability."""
    result = await SolidWorksAdapter.save_body_as_part(
        None, "Boss-Extrude1", "C:/x.sldprt"
    )
    assert not result.is_success
    assert "save_body_as_part" in (result.error or "")


# --- Mock behaviour: mirror the live refusals, observe the side effect ---


@pytest.mark.asyncio
async def test_mock_save_body_writes_a_file(tmp_path) -> None:
    """A valid request writes a placeholder file and echoes the body list."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    target = tmp_path / "body.sldprt"

    result = await adapter.save_body_as_part("Boss-Extrude1", str(target))
    assert result.is_success
    assert os.path.exists(target)
    assert result.data["body"] == "Boss-Extrude1"
    assert result.data["solid_bodies"] == ["Boss-Extrude1"]


@pytest.mark.asyncio
async def test_mock_save_body_rejects_missing_parent_dir(tmp_path) -> None:
    """A target under a non-existent directory is refused, as it is live."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.save_body_as_part(
        "B1", str(tmp_path / "no_such_dir" / "b.sldprt")
    )
    assert not result.is_success
    assert "Parent directory does not exist" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_save_body_requires_a_part(tmp_path) -> None:
    """Called on a drawing, it refuses before touching anything."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_drawing()

    result = await adapter.save_body_as_part("B1", str(tmp_path / "b.sldprt"))
    assert not result.is_success
    assert "requires an active part" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_save_body_requires_body_name(tmp_path) -> None:
    """A blank body name is rejected."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    result = await adapter.save_body_as_part("  ", str(tmp_path / "b.sldprt"))
    assert not result.is_success
    assert "body_name is required" in (result.error or "")
