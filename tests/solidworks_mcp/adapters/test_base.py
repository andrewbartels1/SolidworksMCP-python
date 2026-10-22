"""Tests for base adapter defaults."""

from __future__ import annotations

import inspect
from datetime import datetime
from types import SimpleNamespace

import pytest

from solidworks_mcp.adapters.base import (
    AdapterHealth,
    AdapterResult,
    AdapterResultStatus,
    SolidWorksAdapter,
    SolidWorksFeature,
    SolidWorksModel,
)
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


class _Adapter(SolidWorksAdapter):
    """Minimal concrete adapter for testing defaults."""

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

    async def list_features(self, include_suppressed=True):
        return None

    async def list_configurations(self):
        return None

    async def create_part(self, part_name, template=None, units=None, material=None):
        return None

    async def create_assembly(self, assembly_name, template=None):
        return None

    async def create_drawing(self, drawing_name, template=None, sheet_size=None):
        return None

    async def create_extrusion(
        self,
        depth,
        direction=None,
        reverse=False,
        thin_feature=False,
        thin_thickness=0.0,
        both_directions=False,
        auto_fillet_corners=False,
        fillet_corners_radius=0.0,
    ):
        return None

    async def create_revolve(self, angle, direction=None):
        return None

    async def create_sweep(self, path_sketch, profile_sketch):
        return None

    async def create_loft(self, profile_sketches, guide_curves=None):
        return None

    async def create_sketch(self, plane):
        return None

    async def add_line(self, x1, y1, x2, y2):
        return None

    async def add_circle(self, cx, cy, radius):
        return None

    async def add_rectangle(self, x1, y1, x2, y2):
        return None

    async def exit_sketch(self):
        return None

    async def get_mass_properties(self):
        return None

    async def export_image(self, payload):
        return None

    async def export_file(self, file_path, file_format):
        return None

    async def get_dimension(self, name):
        return None

    async def set_dimension(self, name, value):
        return None


def test_base_config_normalizes_unknown_object() -> None:
    """Non-mapping config objects should normalize to empty dict."""
    # Pass a plain object without model_dump to hit the fallback branch.
    adapter = _Adapter(object())
    assert adapter.config_dict == {}


@pytest.mark.asyncio
async def test_base_default_sketch_helpers_return_error() -> None:
    """Default sketch helper methods should return not-implemented errors."""
    # Exercise default error responses for unimplemented sketch helpers.
    adapter = _Adapter({})

    result = await adapter.add_polygon(0.0, 0.0, 1.0, 5)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.add_ellipse(0.0, 0.0, 2.0, 1.0)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.add_sketch_constraint("e1", None, "coincident")
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_linear_pattern(["e1"], 1.0, 0.0, 5.0, 2)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_circular_pattern(["e1"], 90.0, 4)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_mirror(["e1"], "line1")
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.sketch_offset(["e1"], 1.0, False)
    assert result.status == AdapterResultStatus.ERROR

    result = await adapter.add_chamfer(1.0, ["Edge1"])
    assert result.status == AdapterResultStatus.ERROR
    assert "add_chamfer" in (result.error or "")

    result = await adapter.get_selected_entities()
    assert result.status == AdapterResultStatus.ERROR
    assert "get_selected_entities" in (result.error or "")


class TestAdapterHealthCoverage:
    """Test adapter health coverage."""

    def test_getitem_fallback_unknown_key(self):
        """Line 52 — unknown key falls through to model_dump().get(key)."""
        health = AdapterHealth(
            healthy=True,
            last_check=datetime.now(),
            error_count=0,
            success_count=5,
            average_response_time=0.1,
            connection_status="connected",
        )
        # "success_count" is a real field but not one of the legacy shortcuts
        result = health["success_count"]
        assert result == 5

    def test_getitem_fallback_missing_key_returns_none(self):
        """Test getitem fallback missing key returns none."""

        health = AdapterHealth(
            healthy=True,
            last_check=datetime.now(),
            error_count=0,
            success_count=0,
            average_response_time=0.0,
            connection_status="connected",
        )
        assert health["nonexistent_field"] is None

    def test_contains_nonlegacy_key(self):
        """Line 67 — non-legacy key checked via model_dump()."""
        health = AdapterHealth(
            healthy=True,
            last_check=datetime.now(),
            error_count=0,
            success_count=0,
            average_response_time=0.0,
            connection_status="connected",
        )
        assert "healthy" in health  # real field, not in legacy_keys
        assert "nonexistent" not in health  # not in model_dump either

    def test_contains_legacy_keys_always_true(self):
        """Test contains legacy keys always true."""

        health = AdapterHealth(
            healthy=False,
            last_check=datetime.now(),
            error_count=0,
            success_count=0,
            average_response_time=0.0,
            connection_status="disconnected",
        )
        for key in ("status", "connected", "adapter_type", "version", "uptime"):
            assert key in health

    def test_getitem_status_unhealthy(self):
        """Test getitem status unhealthy."""

        health = AdapterHealth(
            healthy=False,
            last_check=datetime.now(),
            error_count=0,
            success_count=0,
            average_response_time=0.0,
            connection_status="disconnected",
        )
        assert health["status"] == "unhealthy"


class TestSolidWorksFeatureCoverage:
    """Test solid works feature coverage."""

    def test_getitem_returns_parameter_value(self):
        """Line 148-150 — feature["key"] checks parameters first."""
        feature = SolidWorksFeature(
            id="f1",
            name="Boss-Extrude1",
            type="Extrusion",
            parameters={"depth": 10.0},
        )
        assert feature["depth"] == 10.0

    def test_getitem_fallback_to_model_dump(self):
        """Line 150 — unknown key falls through to model_dump()."""
        feature = SolidWorksFeature(id="f1", name="Boss1", type="Extrusion")
        assert feature["name"] == "Boss1"
        assert feature["nonexistent"] is None


class TestAdapterBaseInitCoverage:
    """Test adapter base init coverage."""

    def test_init_with_model_dump_config(self):
        """Line 222 — config with model_dump() method normalized via it."""

        class FakeConfig:
            """Test fake config."""

            def model_dump(self):
                """Test model dump."""

                return {"mock_solidworks": True, "timeout": 30}

        adapter = MockSolidWorksAdapter(FakeConfig())
        assert adapter.config_dict == {"mock_solidworks": True, "timeout": 30}

    @pytest.mark.asyncio
    async def test_save_file_default_not_implemented(self):
        """Line 269 — base save_file returns error."""
        adapter = MockSolidWorksAdapter({})
        # MockSolidWorksAdapter overrides save_file, so call the base directly
        from solidworks_mcp.adapters.base import SolidWorksAdapter

        result = await SolidWorksAdapter.save_file(adapter)
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in result.error

    @pytest.mark.asyncio
    async def test_add_arc_not_implemented(self):
        """Line 378 — base add_arc returns error."""
        from solidworks_mcp.adapters.base import SolidWorksAdapter

        result = await SolidWorksAdapter.add_arc(None, 0, 0, 1, 0, 0, 1)
        assert result.status == AdapterResultStatus.ERROR

    @pytest.mark.asyncio
    async def test_add_spline_not_implemented(self):
        """Line 385 — base add_spline returns error."""
        from solidworks_mcp.adapters.base import SolidWorksAdapter

        result = await SolidWorksAdapter.add_spline(None, [])
        assert result.status == AdapterResultStatus.ERROR

    @pytest.mark.asyncio
    async def test_add_centerline_not_implemented(self):
        """Line 394 — base add_centerline returns error."""
        from solidworks_mcp.adapters.base import SolidWorksAdapter

        result = await SolidWorksAdapter.add_centerline(None, 0, 0, 1, 1)
        assert result.status == AdapterResultStatus.ERROR

    @pytest.mark.asyncio
    async def test_create_cut_not_implemented(self):
        """Line 504 — base create_cut returns error."""
        from solidworks_mcp.adapters.base import SolidWorksAdapter

        result = await SolidWorksAdapter.create_cut(None, "Sketch1", 5.0)
        assert result.status == AdapterResultStatus.ERROR

    def test_get_metrics_returns_copy(self):
        """Line 555 — get_metrics returns a copy."""
        adapter = MockSolidWorksAdapter({})
        metrics = adapter.get_metrics()
        assert "operations_count" in metrics
        metrics["operations_count"] = 9999
        # Original not mutated
        assert adapter.get_metrics()["operations_count"] != 9999

    @pytest.mark.asyncio
    async def test_add_sketch_circle_alias(self):
        """Line 500 — add_sketch_circle delegates to add_circle."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        result = await adapter.add_sketch_circle(0.0, 0.0, 5.0, construction=False)
        assert result.status == AdapterResultStatus.SUCCESS


class _DummyAdapter(SolidWorksAdapter):
    """Test suite for DummyAdapter."""

    async def connect(self):
        """Test helper for connect."""
        return None

    async def disconnect(self):
        """Test helper for disconnect."""
        return None

    def is_connected(self) -> bool:
        """Test helper for is connected."""
        return True

    async def health_check(self) -> AdapterHealth:
        """Test helper for health check."""
        return AdapterHealth(
            healthy=True,
            last_check=datetime.now(),
            error_count=0,
            success_count=1,
            average_response_time=0.01,
            connection_status="connected",
            metrics={"adapter_type": "dummy", "version": "test", "uptime": 1.0},
        )

    async def open_model(self, file_path: str):
        """Test helper for open model."""
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=SolidWorksModel(path=file_path, name="m", type="Part", is_active=True),
        )

    async def close_model(self, save: bool = False):
        """Test helper for close model."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def get_model_info(self):
        """Test helper for get model info."""
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "name": "m",
                "path": "p",
                "type": "Part",
                "configuration": "Default",
            },
        )

    async def list_features(
        self, include_suppressed: bool = False, max_assembly_depth: int = 2
    ):
        """Test helper for list features."""
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=[
                {
                    "name": "Sketch1",
                    "type": "ProfileFeature",
                    "suppressed": False,
                }
            ],
        )

    async def list_configurations(self):
        """Test helper for list configurations."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=["Default"])

    async def create_part(self):
        """Test helper for create part."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_assembly(self):
        """Test helper for create assembly."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_drawing(self):
        """Test helper for create drawing."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_extrusion(self, params):
        """Test helper for create extrusion."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_revolve(self, params):
        """Test helper for create revolve."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_sweep(self, params):
        """Test helper for create sweep."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_loft(self, params):
        """Test helper for create loft."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_sketch(self, plane: str):
        """Test helper for create sketch."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data="Sketch1")

    async def add_line(self, x1: float, y1: float, x2: float, y2: float):
        """Test helper for add line."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data="L1")

    async def add_circle(self, center_x: float, center_y: float, radius: float):
        """Test helper for add circle."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data="C1")

    async def add_rectangle(self, x1: float, y1: float, x2: float, y2: float):
        """Test helper for add rectangle."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data="R1")

    async def exit_sketch(self):
        """Test helper for exit sketch."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def get_mass_properties(self):
        """Test helper for get mass properties."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def export_file(self, file_path: str, format_type: str):
        """Test helper for export file."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def export_image(self, payload: dict):
        """Test helper for export image."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def get_dimension(self, name: str):
        """Test helper for get dimension."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=1.0)

    async def set_dimension(self, name: str, value: float):
        """Test helper for set dimension."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)


def test_adapter_base_legacy_getitem_and_contains():
    """Test adapter base legacy getitem and contains."""
    health = AdapterHealth(
        healthy=True,
        last_check=datetime.now(),
        error_count=0,
        success_count=1,
        average_response_time=0.1,
        connection_status="connected",
        metrics={"adapter_type": "mock", "version": "v1", "uptime": 3.0},
    )
    assert health["status"] == "healthy"
    assert health["connected"] is True
    assert health["adapter_type"] == "mock"
    assert health["version"] == "v1"
    assert health["uptime"] == 3.0
    assert "status" in health

    m = SolidWorksModel(
        path="p", name="n", type="Part", is_active=True, properties={"units": "mm"}
    )
    assert m["title"] == "n"
    assert m["units"] == "mm"


@pytest.mark.asyncio
async def test_base_default_optional_methods_return_not_implemented_errors():
    """Concrete adapters inherit default error responses for optional APIs."""
    adapter = _DummyAdapter({})

    fully_defined = await adapter.check_sketch_fully_defined()
    assert fully_defined.is_error
    assert "not implemented" in (fully_defined.error or "").lower()

    cut = await adapter.create_cut_extrude(SimpleNamespace(depth=1.0))
    assert cut.is_error
    assert "not implemented" in (cut.error or "").lower()

    fillet = await adapter.add_fillet(radius=1.0, edge_names=["Edge<1>"])
    assert fillet.is_error
    assert "not implemented" in (fillet.error or "").lower()


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


CAPABILITIESFeatureEditingCapability = ["delete_feature", "suppress_feature", "rename_feature", "undo"]


@pytest.mark.parametrize("capability", CAPABILITIESFeatureEditingCapability)
@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer_feature_editing(capability: str, cls: type) -> None:
    """A capability missing from a wrapper degrades silently at runtime."""
    method = getattr(cls, capability, None)
    assert method is not None, f"{cls.__name__} is missing {capability}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{capability} must be async"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("capability", CAPABILITIESFeatureEditingCapability)
async def test_base_defaults_report_missing_capability_feature_editing(capability: str) -> None:
    """The base defaults name the missing capability, not a fabrication."""
    method = getattr(SolidWorksAdapter, capability)
    args: tuple[object, ...]
    if capability == "undo":
        args = (1,)
    elif capability == "rename_feature":
        args = ("Feature1", "Feature2")
    else:
        args = ("Feature1",)
    result = await method(None, *args)

    assert not result.is_success
    assert capability in (result.error or "")


CAPABILITY = "check_interference"


@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer_interference(cls: type) -> None:
    """A capability missing from a wrapper degrades silently at runtime."""
    method = getattr(cls, CAPABILITY, None)
    assert method is not None, f"{cls.__name__} is missing {CAPABILITY}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{CAPABILITY} must be async"
    )


@pytest.mark.asyncio
async def test_base_default_reports_the_missing_capability() -> None:
    """The base default names the missing capability, not a fabrication.

    Called unbound: the default never touches ``self``.
    """
    result = await SolidWorksAdapter.check_interference(None, {})

    assert not result.is_success
    assert CAPABILITY in (result.error or "")


CAPABILITYMirrorCapability = "mirror_feature"


@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer_mirror(cls: type) -> None:
    """A capability missing from a wrapper degrades silently at runtime."""
    method = getattr(cls, CAPABILITYMirrorCapability, None)
    assert method is not None, f"{cls.__name__} is missing {CAPABILITYMirrorCapability}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{CAPABILITYMirrorCapability} must be async"
    )


@pytest.mark.asyncio
async def test_base_defaults_report_missing_capability_mirror() -> None:
    """The base adapter's default names the missing capability, not a fabrication."""

    class _BareAdapter(SolidWorksAdapter):
        """Minimal concrete adapter that leaves mirror_feature unimplemented."""

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

    result = await adapter.mirror_feature(["Body1"], "Right Plane")
    assert not result.is_success
    assert "mirror_feature" in (result.error or "")


@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_save_body_as_part_exists_on_every_layer(cls: type) -> None:
    """Every adapter layer defines ``save_body_as_part`` as an async method."""
    method = getattr(cls, "save_body_as_part", None)
    assert method is not None, f"{cls.__name__} is missing save_body_as_part"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.save_body_as_part must be async"
    )


@pytest.mark.asyncio
async def test_base_default_reports_missing_capability() -> None:
    """The base default returns an error naming the missing capability."""
    result = await SolidWorksAdapter.save_body_as_part(
        None, "Boss-Extrude1", "C:/x.sldprt"
    )
    assert not result.is_success
    assert "save_body_as_part" in (result.error or "")


CAPABILITIESOpenDocumentsCapability = ["list_open_documents", "activate_document"]


@pytest.mark.parametrize("capability", CAPABILITIESOpenDocumentsCapability)
@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer_open_documents(capability: str, cls: type) -> None:
    """Every adapter layer defines the capability as an async method."""
    method = getattr(cls, capability, None)
    assert method is not None, f"{cls.__name__} is missing {capability}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{capability} must be async"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("capability", CAPABILITIESOpenDocumentsCapability)
async def test_base_defaults_report_missing_capability_open_documents(capability: str) -> None:
    """The base default returns an error that names the missing capability."""
    method = getattr(SolidWorksAdapter, capability)
    result = await (
        method(None)
        if capability == "list_open_documents"
        else method(None, "whatever")
    )
    assert not result.is_success
    assert capability in (result.error or "")


CAPABILITYPatternCapability = "pattern_circular"


@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer_pattern(cls: type) -> None:
    """A capability missing from a wrapper degrades silently at runtime."""
    method = getattr(cls, CAPABILITYPatternCapability, None)
    assert method is not None, f"{cls.__name__} is missing {CAPABILITYPatternCapability}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{CAPABILITYPatternCapability} must be async"
    )


@pytest.mark.asyncio
async def test_base_defaults_report_missing_capability_pattern() -> None:
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


#: Reference-geometry capabilities on ``SolidWorksFeaturesMixin``.
CAPABILITIESReferenceGeometryCapability = [
    "create_reference_plane",
    "create_axis",
    "create_reference_point",
]


@pytest.mark.parametrize("capability", CAPABILITIESReferenceGeometryCapability)
@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer_reference_geometry(capability: str, cls: type) -> None:
    """A capability missing from a wrapper degrades silently at runtime."""
    method = getattr(cls, capability, None)
    assert method is not None, f"{cls.__name__} is missing {capability}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{capability} must be async"
    )


@pytest.mark.asyncio
async def test_base_defaults_report_missing_capability_reference_geometry() -> None:
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

    point_result = await adapter.create_reference_point("face_center", 0.0, 0.0, 0.0)
    assert not point_result.is_success
    assert "create_reference_point" in (point_result.error or "")


@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_set_units_exists_on_every_layer(cls: type) -> None:
    """Every adapter layer defines ``set_units`` as an async method."""
    method = getattr(cls, "set_units", None)
    assert method is not None, f"{cls.__name__} is missing set_units"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.set_units must be async"
    )


@pytest.mark.asyncio
async def test_base_default_reports_missing_capability_set_units() -> None:
    """The base default returns an error naming the missing capability."""
    result = await SolidWorksAdapter.set_units(None, "mm")
    assert not result.is_success
    assert "set_units" in (result.error or "")


#: Capabilities added on this branch. These names are a contract with the
#: gates in ``tools/drawing.py`` — see the module docstring.
CAPABILITIESDrawingCapabilities = [
    "create_drawing_view",
    "add_drawing_view",
    "create_technical_drawing",
    "add_note",
    "list_drawing_views",
    "auto_center_marks",
]


#: Capabilities a tool on this branch already reaches. ``tools/drawing.py``
#: guards each tool with ``require_capability(adapter, "<name>", ...)``, so a rename here
#: leaves the tool refusing forever with every adapter test still green.
GATED_ON_THIS_BRANCH = [
    "add_drawing_view",
    "create_technical_drawing",
    "auto_center_marks",
]


#: Capabilities whose tool gates arrive with the refuse-instead-of-fabricate
#: change. The names are chosen to match those gates exactly so that neither
#: branch has to touch ``tools/drawing.py`` — the tools light up when both
#: land. Until then these adapter methods are reachable only by direct call.
GATED_ONCE_REFUSAL_PR_LANDS = [
    "create_drawing_view",
    "add_note",
]


@pytest.mark.parametrize("capability", CAPABILITIESDrawingCapabilities)
@pytest.mark.parametrize("cls", WRAPPERS, ids=lambda c: c.__name__)
def test_capability_exists_on_every_layer_drawing(capability: str, cls: type) -> None:
    """A capability missing from a wrapper degrades silently at runtime."""
    method = getattr(cls, capability, None)
    assert method is not None, f"{cls.__name__} is missing {capability}"
    assert inspect.iscoroutinefunction(method), (
        f"{cls.__name__}.{capability} must be async"
    )


def test_every_capability_is_accounted_for() -> None:
    """No capability may be added without deciding how a tool reaches it.

    An adapter method no tool can call is dead weight; this forces the choice
    to be explicit rather than forgotten.
    """
    classified = set(GATED_ON_THIS_BRANCH) | set(GATED_ONCE_REFUSAL_PR_LANDS)
    unclassified = set(CAPABILITIESDrawingCapabilities) - classified - {"list_drawing_views"}
    assert not unclassified, (
        f"{sorted(unclassified)} reach no tool and are not recorded as "
        "pending; add the gate or say why it is deferred"
    )


def test_dimension_import_is_not_claimed_as_a_capability() -> None:
    """``auto_dimension_view`` is deliberately absent, and must stay absent.

    ``IDrawingDoc::InsertModelAnnotations3`` could not be made to insert
    anything on SW 2025: it returns ``None`` with the view selected and
    activated, for both ``swInsertDimensions`` and
    ``swInsertDimensionsMarkedForDrawing``, with ``AllViews`` either way, on
    front and top views, against a part carrying a real sketch dimension, and
    after a ``ForceRebuild3``. ``IView::GetDisplayDimensionCount`` stayed 0
    throughout.

    Shipping it anyway would mean shipping a capability never observed to
    work — the exact failure this branch exists to correct. This test fails
    if someone adds it back without live proof.
    """
    from solidworks_mcp.adapters.base import SolidWorksAdapter as _Base

    assert not hasattr(_Base, "auto_dimension_view"), (
        "auto_dimension_view is back on the adapter surface; it must not "
        "ship until InsertModelAnnotations3 is shown to insert a dimension "
        "against real SolidWorks"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("capability", CAPABILITIESDrawingCapabilities)
async def test_base_defaults_report_missing_capability_drawing(capability: str) -> None:
    """The base defaults name the missing capability, not a fabrication.

    Called unbound: these defaults never touch ``self``, so this avoids
    standing up a concrete subclass just to reach them.
    """
    method = getattr(SolidWorksAdapter, capability)
    result = await (
        method(None) if capability == "list_drawing_views" else method(None, {})
    )

    assert not result.is_success
    assert capability in (result.error or ""), (
        f"the default for {capability} does not name the missing capability"
    )
