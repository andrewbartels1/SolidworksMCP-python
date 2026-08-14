"""Contract tests for the assembly capabilities added to the adapter surface.

``insert_component``, ``list_components`` and ``add_mate`` each exist on the
base adapter, the mock, the circuit breaker and the connection pool. A method
missing from either wrapper silently degrades to the base "not implemented"
default at runtime, and mock mode cannot catch it — the mock is not wrapped —
so the wiring is asserted directly here.

Modeled on ``test_new_capabilities.py`` from the
``feat/feature-editing-and-breaker-isolation`` branch, scoped to just the
three capabilities introduced on this branch.
"""

import inspect

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

#: Capabilities added on this branch.
CAPABILITIES = [
    "insert_component",
    "list_components",
    "add_mate",
]

WRAPPERS = [
    SolidWorksAdapter,
    MockSolidWorksAdapter,
    CircuitBreakerAdapter,
    ConnectionPoolAdapter,
]


@pytest.mark.parametrize("capability", CAPABILITIES)
@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer(capability: str, cls: type) -> None:
    """A capability missing from a wrapper degrades silently at runtime."""
    method = getattr(cls, capability, None)
    assert method is not None, f"{cls.__name__} is missing {capability}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{capability} must be async"
    )


@pytest.mark.parametrize("capability", CAPABILITIES)
def test_real_adapter_resolves_to_the_com_mixin(capability: str) -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub.

    The mixin methods are only reachable if they are defined *inside*
    ``SolidWorksIOMixin``. Written at module scope in ``io.py`` they still
    import cleanly, still pass every mock test, and still satisfy the
    layer checks above — but ``PyWin32Adapter`` then resolves the name to
    ``SolidWorksAdapter``'s "not implemented" default and the real COM code
    is never called. That happened while building this branch, and only
    showed up under runtime MRO inspection.
    """
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (klass.__name__ for klass in PyWin32Adapter.__mro__ if capability in vars(klass)),
        None,
    )
    assert owner == "SolidWorksIOMixin", (
        f"PyWin32Adapter.{capability} resolves to {owner}, not the COM mixin. "
        "The implementation is unreachable and every call silently returns the "
        "base adapter's 'not implemented' error."
    )


@pytest.mark.parametrize("capability", CAPABILITIES)
def test_wrappers_do_not_silently_fall_through_to_base(capability: str) -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert capability in vars(cls), (
            f"{cls.__name__} inherits {capability} from the base adapter, so "
            "calls to it return 'not implemented' instead of reaching the real "
            "adapter"
        )


@pytest.mark.asyncio
async def test_mock_insert_component_records_and_lists() -> None:
    """insert_component records state that list_components reflects back."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    first = await adapter.insert_component("C:/parts/a.sldprt")
    assert first.is_success
    assert first.data["component"] == "component-1"
    assert first.data["components_before"] == 0
    assert first.data["components_after"] == 1

    second = await adapter.insert_component("C:/parts/b.sldprt", x=10.0)
    assert second.is_success
    assert second.data["component"] == "component-2"
    assert second.data["components_before"] == 1
    assert second.data["components_after"] == 2

    listed = await adapter.list_components()
    assert listed.is_success
    assert listed.data == ["component-1", "component-2"]


@pytest.mark.asyncio
async def test_mock_add_mate_reports_the_mate() -> None:
    """add_mate on the mock reports the components and mate type back."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.add_mate("part-1", "part-2", mate_type="concentric")
    assert result.is_success
    assert result.data["components"] == ["part-1", "part-2"]
    assert result.data["mate_type"] == "concentric"


@pytest.mark.asyncio
async def test_mock_does_not_claim_geometry_moved() -> None:
    """The mock must not answer the "did it really work" question with True.

    ``geometry_moved`` is the field that separates a mate which positioned
    a component from one SolidWorks accepted and ignored. The mock has no
    geometry, so the only honest answer is "not determinable".
    """
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.add_mate("part-1", "part-2")
    assert result.is_success
    assert result.data["geometry_moved"] is None, (
        "the mock reported a geometry check it cannot perform"
    )
    assert result.data["moved_components"] == []


def test_mock_mate_types_match_the_com_layer() -> None:
    """The mock's accepted mate types must match the COM implementation.

    The two lists are maintained separately, so a mate type added to the COM
    layer alone would be rejected in mock mode and accepted live -- and the
    whole test suite runs against the mock.
    """
    from solidworks_mcp.adapters.solidworks.io import _MATE_TYPES

    source = inspect.getsource(MockSolidWorksAdapter.add_mate)
    for mate_type in _MATE_TYPES:
        assert f'"{mate_type}"' in source, (
            f"the COM layer supports the {mate_type!r} mate but the mock "
            "rejects it, so no test can cover it"
        )


@pytest.mark.asyncio
async def test_mock_add_mate_rejects_unknown_mate_type() -> None:
    """An unknown mate type is a validation error, not a fabricated success."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.add_mate("part-1", "part-2", mate_type="bogus")
    assert not result.is_success


@pytest.mark.asyncio
async def test_base_defaults_report_missing_capability() -> None:
    """The base adapter's defaults name the missing capability, not a fabrication."""

    class _BareAdapter(SolidWorksAdapter):
        """Minimal concrete adapter that leaves the new capabilities unimplemented."""

        async def connect(self) -> None:
            return None

        async def disconnect(self) -> None:
            return None

        def is_connected(self) -> bool:
            return False

        async def health_check(self):
            return None

        async def open_model(self, file_path):
            return None

        async def close_model(self, save=False):
            return None

        async def get_model_info(self):
            return None

        async def list_features(self, include_suppressed=False, max_assembly_depth=2):
            return None

        async def list_configurations(self):
            return None

        async def create_part(self, name=None, units=None):
            return None

        async def create_assembly(self, name=None):
            return None

        async def create_drawing(self, name=None):
            return None

        async def create_extrusion(self, params):
            return None

        async def create_revolve(self, params):
            return None

        async def create_sweep(self, params):
            return None

        async def create_loft(self, params):
            return None

        async def create_sketch(self, plane):
            return None

        async def add_line(self, x1, y1, x2, y2):
            return None

        async def add_circle(self, center_x, center_y, radius):
            return None

        async def add_rectangle(self, x1, y1, x2, y2):
            return None

        async def exit_sketch(self):
            return None

        async def get_mass_properties(self):
            return None

        async def export_image(self, payload):
            return None

        async def export_file(self, file_path, format_type):
            return None

        async def get_dimension(self, name):
            return None

        async def set_dimension(self, name, value):
            return None

    adapter = _BareAdapter()

    insert_result = await adapter.insert_component("C:/parts/a.sldprt")
    assert not insert_result.is_success
    assert "insert_component" in (insert_result.error or "")

    list_result = await adapter.list_components()
    assert not list_result.is_success
    assert "list_components" in (list_result.error or "")

    mate_result = await adapter.add_mate("a", "b")
    assert not mate_result.is_success
    assert "add_mate" in (mate_result.error or "")
