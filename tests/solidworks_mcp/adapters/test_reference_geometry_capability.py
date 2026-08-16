"""Contract tests for the reference-geometry capabilities on the adapter surface.

``create_reference_plane`` and ``create_axis`` each exist on the base adapter,
the mock, the circuit breaker and the connection pool. A method missing from
either wrapper silently degrades to the base "not implemented" default at
runtime, and mock mode cannot catch it — the mock is not wrapped — so the
wiring is asserted directly here.

Modeled on ``test_new_capabilities.py``, scoped to the two capabilities
implemented on ``SolidWorksFeaturesMixin`` in
``src/solidworks_mcp/adapters/solidworks/features.py``
(``_create_reference_plane_impl`` / ``_create_axis_impl``).
"""

import inspect

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

#: Capabilities added on this branch.
CAPABILITIES = [
    "create_reference_plane",
    "create_axis",
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
def test_real_adapter_resolves_to_the_features_mixin(capability: str) -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub.

    The mixin methods are only reachable if they are defined *inside*
    ``SolidWorksFeaturesMixin``. Written at module scope in ``features.py``
    they still import cleanly, still pass every mock test, and still satisfy
    the layer checks above — but ``PyWin32Adapter`` then resolves the name to
    ``SolidWorksAdapter``'s "not implemented" default and the real COM code
    is never called.
    """
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (klass.__name__ for klass in PyWin32Adapter.__mro__ if capability in vars(klass)),
        None,
    )
    assert owner == "SolidWorksFeaturesMixin", (
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

    plane_result = await adapter.create_reference_plane("Front Plane", offset=10.0)
    assert not plane_result.is_success
    assert "create_reference_plane" in (plane_result.error or "")

    axis_result = await adapter.create_axis("x")
    assert not axis_result.is_success
    assert "create_axis" in (axis_result.error or "")


# --- Mock refusals: must mirror the live adapter, never fabricate a result ---


@pytest.mark.asyncio
async def test_mock_create_reference_plane_rejects_nonzero_angle() -> None:
    """An angled plane needs a second reference this signature cannot supply."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_reference_plane("Front Plane", offset=10.0, angle=15.0)
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_create_reference_plane_rejects_zero_offset() -> None:
    """A plane coincident with its reference is not a useful result."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_reference_plane("Front Plane", offset=0.0)
    assert not result.is_success


@pytest.mark.asyncio
async def test_mock_create_axis_rejects_unknown_reference() -> None:
    """Only x/y/z are valid axis directions."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_axis("diagonal")
    assert not result.is_success


# --- Mock success shapes ---


@pytest.mark.asyncio
async def test_mock_create_reference_plane_success_shape() -> None:
    """Success invents a sequential plane name and a features_before/after pair."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    first = await adapter.create_reference_plane("Front Plane", offset=76.2)
    assert first.is_success
    assert first.data["name"] == "Plane1"
    assert first.data["reference"] == "Front Plane"
    assert first.data["offset"] == 76.2
    assert first.data["angle"] is None
    assert first.data["flip"] is False
    assert first.data["features_after"] == first.data["features_before"] + 1

    second = await adapter.create_reference_plane("Top Plane", offset=-10.0, flip=True)
    assert second.is_success
    assert second.data["name"] == "Plane2"
    assert second.data["flip"] is True
    assert second.data["features_after"] == second.data["features_before"] + 1
    # The mock's feature-tree counter accumulates across calls, same as a
    # live SolidWorks model whose feature count only grows.
    assert second.data["features_before"] == first.data["features_after"]


@pytest.mark.asyncio
async def test_mock_create_axis_success_shape() -> None:
    """Success reports the plane pair and a features_before/after pair that differ by 1."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_axis("+X")
    assert result.is_success
    assert result.data["reference"] == "x"
    assert result.data["planes"] == ["Top Plane", "Front Plane"]
    assert result.data["features_after"] == result.data["features_before"] + 1


@pytest.mark.asyncio
async def test_mock_create_axis_plane_pairs_match_the_com_layer() -> None:
    """The mock's plane pairs must match the COM layer's ``_AXIS_PLANE_PAIRS``.

    The two are the same object (imported directly, not copied), so this
    also guards against a future refactor accidentally duplicating and
    diverging the mapping.
    """
    from solidworks_mcp.adapters.solidworks.features import _AXIS_PLANE_PAIRS

    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    for direction, (plane_a, plane_b) in _AXIS_PLANE_PAIRS.items():
        result = await adapter.create_axis(direction)
        assert result.is_success
        assert result.data["planes"] == [plane_a, plane_b]
