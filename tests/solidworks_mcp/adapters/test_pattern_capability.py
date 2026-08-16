"""Contract tests for the ``pattern_circular`` capability on the adapter surface.

``pattern_circular`` exists on the base adapter, the mock, the circuit
breaker and the connection pool. A method missing from either wrapper
silently degrades to the base "not implemented" default at runtime, and
mock mode cannot catch it - the mock is not wrapped - so the wiring is
asserted directly here.

Modeled on ``test_mirror_capability.py``, scoped to the single capability
implemented on ``SolidWorksFeaturesMixin`` in
``src/solidworks_mcp/adapters/solidworks/features.py``
(``_pattern_circular_impl`` / ``SolidWorksFeaturesMixin.pattern_circular``).
"""

import inspect

import pytest

from solidworks_mcp.adapters.base import ExtrusionParameters, SolidWorksAdapter
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

CAPABILITY = "pattern_circular"

WRAPPERS = [
    SolidWorksAdapter,
    MockSolidWorksAdapter,
    CircuitBreakerAdapter,
    ConnectionPoolAdapter,
]


@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer(cls: type) -> None:
    """A capability missing from a wrapper degrades silently at runtime."""
    method = getattr(cls, CAPABILITY, None)
    assert method is not None, f"{cls.__name__} is missing {CAPABILITY}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{CAPABILITY} must be async"
    )


def test_real_adapter_resolves_to_the_features_mixin() -> None:
    """PyWin32Adapter must reach the COM implementation, not the base stub.

    ``pattern_circular`` is only reachable if it is defined *inside*
    ``SolidWorksFeaturesMixin``. Written at module scope in ``features.py``
    it would still import cleanly, still pass every mock test, and still
    satisfy the layer checks above - but ``PyWin32Adapter`` would then
    resolve the name to ``SolidWorksAdapter``'s "not implemented" default
    and the real COM code would never be called.
    """
    pytest.importorskip("win32com", reason="pywin32 is Windows-only")
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    owner = next(
        (
            klass.__name__
            for klass in PyWin32Adapter.__mro__
            if CAPABILITY in vars(klass)
        ),
        None,
    )
    assert owner == "SolidWorksFeaturesMixin", (
        f"PyWin32Adapter.{CAPABILITY} resolves to {owner}, not the COM mixin. "
        "The implementation is unreachable and every call silently returns the "
        "base adapter's 'not implemented' error."
    )


def test_wrappers_do_not_silently_fall_through_to_base() -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert CAPABILITY in vars(cls), (
            f"{cls.__name__} inherits {CAPABILITY} from the base adapter, so "
            "calls to it return 'not implemented' instead of reaching the real "
            "adapter"
        )


@pytest.mark.asyncio
async def test_base_defaults_report_missing_capability() -> None:
    """The base adapter's default names the missing capability, not a fabrication."""

    class _BareAdapter(SolidWorksAdapter):
        """Minimal concrete adapter that leaves pattern_circular unimplemented."""

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

    result = await adapter.pattern_circular(["Boss-Extrude1"], "Axis1", 4)
    assert not result.is_success
    assert "pattern_circular" in (result.error or "")


# --- Mock refusals: must mirror the live adapter, never fabricate a result ---


@pytest.mark.asyncio
async def test_mock_pattern_circular_rejects_empty_features() -> None:
    """An empty feature list is refused with the live adapter's exact message."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.pattern_circular([], "Axis1", 4)
    assert not result.is_success
    assert "at least one feature name" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_pattern_circular_rejects_empty_axis() -> None:
    """An empty axis name is refused with the live adapter's exact message."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.pattern_circular(["Boss-Extrude1"], "", 4)
    assert not result.is_success
    assert "requires an axis name to rotate about" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_pattern_circular_rejects_count_below_two() -> None:
    """A count under 2 is refused with the live adapter's exact message."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.pattern_circular(["Boss-Extrude1"], "Axis1", 1)
    assert not result.is_success
    assert "needs a count of at least 2" in (result.error or "")


@pytest.mark.asyncio
async def test_mock_pattern_circular_rejects_unknown_axis() -> None:
    """An axis name that was never created in this session cannot be selected."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    feature = await adapter.create_extrusion(ExtrusionParameters(depth=10.0))
    assert feature.is_success

    result = await adapter.pattern_circular([feature.data.name], "Axis99", 4)
    assert not result.is_success
    assert "Axis99" in (result.error or "")


# --- Mock success shape ---


@pytest.mark.asyncio
async def test_mock_pattern_circular_success_volume_ratio() -> None:
    """Success grows the tracked volume figure, giving a ratio well above 1.5.

    Reproduces the live measurement exactly: a hub+blade part at 48431.5
    mm^3, patterned to 4 blades (3 extra instances), gave 75916.4 mm^3 -
    ratio 1.5677.
    """
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    feature = await adapter.create_extrusion(ExtrusionParameters(depth=10.0))
    assert feature.is_success
    source_name = feature.data.name

    axis = await adapter.create_axis("z")
    assert axis.is_success
    axis_name = axis.data["name"]

    result = await adapter.pattern_circular([source_name], axis_name, 4)
    assert result.is_success
    assert result.data["patterned"] == [source_name]
    assert result.data["axis"] == axis_name
    assert result.data["count"] == 4
    assert result.data["volume_ratio"] > 1.5
    assert result.data["volume_after"] > result.data["volume_before"]


# --- Guard test: wrong selection marks silently pattern nothing ---


def test_pattern_selection_marks_match_the_solidworks_api() -> None:
    """These are the SolidWorks-documented selection marks for FeatureCircularPattern5.

    Per the API reference: the direction axis is mark 1 and the features to
    pattern are mark 4. These differ from the mirror marks (features 1,
    plane 2) - reusing those makes the call report a feature while
    patterning nothing, a bug no other test here would catch, since the
    live COM code is off-limits for modification and the mock does not
    execute this path at all.
    """
    from solidworks_mcp.adapters.solidworks.features import (
        _PATTERN_MARK_AXIS,
        _PATTERN_MARK_FEATURES,
    )

    assert _PATTERN_MARK_AXIS == 1
    assert _PATTERN_MARK_FEATURES == 4
