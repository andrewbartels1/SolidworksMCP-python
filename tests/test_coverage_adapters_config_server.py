"""
Branch-coverage tests for:
  - src/solidworks_mcp/adapters/base.py
  - src/solidworks_mcp/adapters/circuit_breaker.py
  - src/solidworks_mcp/adapters/mock_adapter.py
  - src/solidworks_mcp/config.py
  - src/solidworks_mcp/__init__.py
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel

import pytest

from src.solidworks_mcp.adapters.base import (
    AdapterHealth,
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
    SolidWorksFeature,
)
from src.solidworks_mcp.adapters.circuit_breaker import (
    CircuitBreakerAdapter,
    CircuitState,
)
from src.solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter, _BoolCallable
from src.solidworks_mcp.config import AdapterType, SolidWorksMCPConfig, load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_health(healthy: bool = True, connection_status: str = "connected") -> AdapterHealth:
    return AdapterHealth(
        healthy=healthy,
        last_check=datetime.now(),
        error_count=0,
        success_count=1,
        average_response_time=0.01,
        connection_status=connection_status,
    )


# ---------------------------------------------------------------------------
# 1. base.py
# ---------------------------------------------------------------------------

class TestAdapterHealthGetitem:
    """Covers AdapterHealth.__getitem__ and __contains__ uncovered branches."""

    def test_getitem_unknown_key_returns_model_dump_value(self):
        """Line 52: fallback to model_dump().get(key) for unknown keys."""
        health = _make_health()
        # 'healthy' is a real field but not a legacy key — hits line 52
        assert health["healthy"] is True

    def test_getitem_unknown_key_missing_returns_none(self):
        """Line 52: model_dump().get() returns None for absent keys."""
        health = _make_health()
        assert health["nonexistent_field_xyz"] is None

    def test_contains_nonlegacy_field_present(self):
        """Line 67: key in model_dump() for a real model field."""
        health = _make_health()
        # 'healthy' is not in the legacy set, hits line 67
        assert "healthy" in health

    def test_contains_nonlegacy_field_absent(self):
        """Line 67: key not in model_dump() and not in legacy set."""
        health = _make_health()
        assert "totally_made_up_key" not in health

    def test_contains_legacy_keys_short_circuit(self):
        """Lines 64-66: legacy keys return True without hitting line 67."""
        health = _make_health()
        for key in ("status", "connected", "adapter_type", "version", "uptime"):
            assert key in health


class TestSolidWorksFeatureGetitem:
    """Covers SolidWorksFeature.__getitem__ uncovered branch."""

    def test_getitem_key_not_in_parameters_falls_back_to_model_dump(self):
        """Line 150: key absent from parameters hits model_dump().get(key)."""
        feature = SolidWorksFeature(
            name="Boss-Extrude1",
            type="Extrusion",
            parameters={"depth": 10.0},
        )
        # 'name' is a model field but not in parameters — line 150
        assert feature["name"] == "Boss-Extrude1"

    def test_getitem_key_in_parameters_returned_directly(self):
        """Parameters lookup short-circuits before line 150."""
        feature = SolidWorksFeature(
            name="Boss-Extrude1",
            type="Extrusion",
            parameters={"depth": 25.0},
        )
        assert feature["depth"] == 25.0

    def test_getitem_key_absent_everywhere_returns_none(self):
        """Line 150: absent key from both parameters and model_dump."""
        feature = SolidWorksFeature(name="F1", type="T1", parameters={})
        assert feature["zzz_no_such_key"] is None


class TestSolidWorksAdapterInitConfig:
    """Covers SolidWorksAdapter.__init__ config normalisation — line 222."""

    def test_init_with_pydantic_model_config(self):
        """Line 222: config has model_dump() -> normalized via model_dump()."""

        class _PydanticConf(BaseModel):
            mock_connect_delay: float = 0.0
            mock_model_delay: float = 0.0
            mock_feature_delay: float = 0.0
            mock_sketch_delay: float = 0.0

        cfg = _PydanticConf()
        adapter = MockSolidWorksAdapter(cfg)
        # config stored as-is, config_dict populated from model_dump
        assert adapter.config is cfg
        assert "mock_connect_delay" in adapter.config_dict

    def test_init_with_none_config(self):
        """config=None -> config_dict is empty dict."""
        adapter = MockSolidWorksAdapter(None)
        assert adapter.config_dict == {}

    def test_init_with_unknown_object_config(self):
        """config with no model_dump and not a Mapping -> config_dict empty."""

        class _Opaque:
            pass

        adapter = MockSolidWorksAdapter(_Opaque())
        assert adapter.config_dict == {}


class TestAdapterBaseDefaultMethods:
    """Covers default (not-implemented) methods and get_metrics on the base."""

    @pytest.mark.asyncio
    async def test_save_file_default_returns_error(self):
        """Line 269: base save_file returns error result."""
        # Use MockSolidWorksAdapter which overrides save_file; call the base
        # implementation explicitly via super()
        from src.solidworks_mcp.adapters.base import SolidWorksAdapter

        adapter = MockSolidWorksAdapter({})
        # Mock adapter overrides save_file, so reach the base directly
        result = await SolidWorksAdapter.save_file(adapter)
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_arc_default_returns_error(self):
        """Line 378: base add_arc returns error."""
        from src.solidworks_mcp.adapters.base import SolidWorksAdapter

        adapter = MockSolidWorksAdapter({})
        result = await SolidWorksAdapter.add_arc(adapter, 0, 0, 1, 0, 0, 1)
        assert result.status == AdapterResultStatus.ERROR
        assert "add_arc" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_spline_default_returns_error(self):
        """Line 385: base add_spline returns error."""
        from src.solidworks_mcp.adapters.base import SolidWorksAdapter

        adapter = MockSolidWorksAdapter({})
        result = await SolidWorksAdapter.add_spline(adapter, [{"x": 0.0, "y": 0.0}])
        assert result.status == AdapterResultStatus.ERROR
        assert "add_spline" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_centerline_default_returns_error(self):
        """Line 394: base add_centerline returns error (mock overrides it)."""
        from src.solidworks_mcp.adapters.base import SolidWorksAdapter

        adapter = MockSolidWorksAdapter({})
        result = await SolidWorksAdapter.add_centerline(adapter, 0, 0, 1, 1)
        assert result.status == AdapterResultStatus.ERROR
        assert "add_centerline" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_ellipse_default_returns_error(self):
        """Line 425: base add_ellipse returns error."""
        from src.solidworks_mcp.adapters.base import SolidWorksAdapter

        adapter = MockSolidWorksAdapter({})
        result = await SolidWorksAdapter.add_ellipse(adapter, 0, 0, 5.0, 3.0)
        assert result.status == AdapterResultStatus.ERROR
        assert "add_ellipse" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_sketch_circle_alias_calls_add_circle(self):
        """Line 500: add_sketch_circle delegates to add_circle."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_sketch("Front")
        result = await adapter.add_sketch_circle(0.0, 0.0, 5.0)
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_create_cut_default_returns_error(self):
        """Line 504: base create_cut returns error."""
        from src.solidworks_mcp.adapters.base import SolidWorksAdapter

        adapter = MockSolidWorksAdapter({})
        result = await SolidWorksAdapter.create_cut(adapter, "Sketch1", 10.0)
        assert result.status == AdapterResultStatus.ERROR
        assert "create_cut" in (result.error or "")

    def test_get_metrics_returns_copy(self):
        """Line 555: get_metrics returns a copy, not the same dict object."""
        adapter = MockSolidWorksAdapter({})
        m1 = adapter.get_metrics()
        m2 = adapter.get_metrics()
        assert m1 == m2
        assert m1 is not m2


# ---------------------------------------------------------------------------
# 2. circuit_breaker.py
# ---------------------------------------------------------------------------

class TestCircuitBreakerAdapterTransitions:
    """Covers uncovered circuit breaker state transition branches."""

    def _make_cb(self, threshold: int = 3) -> CircuitBreakerAdapter:
        inner = MockSolidWorksAdapter({"mock_connect_delay": 0.0, "mock_model_delay": 0.0})
        return CircuitBreakerAdapter(adapter=inner, failure_threshold=threshold, recovery_timeout=9999)

    def _force_open(self, cb: CircuitBreakerAdapter) -> None:
        """Drive the circuit from CLOSED to OPEN by injecting failures."""
        for _ in range(cb.failure_threshold):
            cb._record_failure()

    def test_record_failure_closed_to_open_transition(self):
        """Lines 120-128: CLOSED -> OPEN when failure_count >= threshold."""
        cb = self._make_cb(threshold=3)
        assert cb.state == CircuitState.CLOSED
        self._force_open(cb)
        assert cb.state == CircuitState.OPEN

    def test_record_failure_half_open_to_open_transition(self):
        """Lines 117-119: HALF_OPEN -> OPEN on failure."""
        cb = self._make_cb(threshold=1)
        self._force_open(cb)
        assert cb.state == CircuitState.OPEN
        # Simulate time passage so _should_allow_request transitions to HALF_OPEN
        cb.last_failure_time = time.time() - cb.recovery_timeout - 1
        assert cb._should_allow_request()  # triggers HALF_OPEN internally
        assert cb.state == CircuitState.HALF_OPEN
        cb._record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_connect_circuit_open_raises(self):
        """Lines 165-166: connect raises when circuit is open."""
        cb = self._make_cb(threshold=1)
        self._force_open(cb)
        with pytest.raises(Exception, match="Circuit breaker"):
            await cb.connect()

    @pytest.mark.asyncio
    async def test_connect_success_records_success(self):
        """Lines 168-170: connect succeeds, _record_success called."""
        cb = self._make_cb()
        await cb.connect()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_connect_inner_failure_records_failure_and_reraises(self):
        """Lines 171-173: connect inner failure -> _record_failure, re-raises."""
        from unittest.mock import AsyncMock

        inner = MockSolidWorksAdapter({})
        inner.connect = AsyncMock(side_effect=RuntimeError("boom"))
        cb = CircuitBreakerAdapter(adapter=inner, failure_threshold=5, recovery_timeout=9999)
        with pytest.raises(RuntimeError, match="boom"):
            await cb.connect()
        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_health_check_circuit_open_marks_unhealthy(self):
        """Lines 196-198: open circuit -> healthy=False, status=circuit_breaker_open."""
        cb = self._make_cb(threshold=1)
        await cb.adapter.connect()
        self._force_open(cb)
        health = await cb.health_check()
        assert health.healthy is False
        assert health.connection_status == "circuit_breaker_open"

    @pytest.mark.asyncio
    async def test_get_model_info_via_circuit_breaker(self):
        """Line 235 area: get_model_info routed through circuit breaker."""
        cb = self._make_cb()
        await cb.connect()
        await cb.adapter.create_part()
        result = await cb.get_model_info()
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_list_features_via_circuit_breaker(self):
        """Line 375 area: list_features routed through circuit breaker."""
        cb = self._make_cb()
        await cb.connect()
        await cb.adapter.create_part()
        result = await cb.list_features()
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_list_configurations_via_circuit_breaker(self):
        """Line 382 area: list_configurations routed through circuit breaker."""
        cb = self._make_cb()
        await cb.connect()
        await cb.adapter.create_part()
        result = await cb.list_configurations()
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_get_mass_properties_via_circuit_breaker(self):
        """Line 367 area: get_mass_properties routed through circuit breaker."""
        cb = self._make_cb()
        await cb.connect()
        await cb.adapter.create_part()
        result = await cb.get_mass_properties()
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_execute_blocked_when_open_returns_error_result(self):
        """Line 269 area: _execute_with_circuit_breaker returns error when circuit open."""
        cb = self._make_cb(threshold=1)
        self._force_open(cb)
        result = await cb.list_configurations()
        assert result.status == AdapterResultStatus.ERROR
        assert "open" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# 3. mock_adapter.py
# ---------------------------------------------------------------------------

class TestBoolCallable:
    """Covers _BoolCallable.__call__ (line 52)."""

    def test_call_returns_bool_true(self):
        """Line 52: calling the instance invokes the getter."""
        bc = _BoolCallable(lambda: True)
        assert bc() is True

    def test_call_returns_bool_false(self):
        bc = _BoolCallable(lambda: False)
        assert bc() is False

    def test_bool_coercion(self):
        """__bool__ path (line 61)."""
        bc = _BoolCallable(lambda: 1)
        assert bool(bc) is True


class TestMockAdapterModelInfo:
    """Covers get_model_info success path (lines 237-252)."""

    @pytest.mark.asyncio
    async def test_get_model_info_with_active_model(self):
        """Lines 237-252: get_model_info returns info when model is active."""
        adapter = MockSolidWorksAdapter({"mock_connect_delay": 0.0, "mock_model_delay": 0.0})
        await adapter.connect()
        await adapter.create_part("TestPart")
        result = await adapter.get_model_info()
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data is not None
        assert result.data["title"] == "TestPart"
        assert result.data["type"] == "Part"

    @pytest.mark.asyncio
    async def test_get_model_info_no_active_model_returns_error(self):
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        result = await adapter.get_model_info()
        assert result.status == AdapterResultStatus.ERROR


class TestMockAdapterListFeatures:
    """Covers list_features with actual features (lines 268-297)."""

    @pytest.mark.asyncio
    async def test_list_features_with_real_features(self):
        """Lines 286-295: features dict populated -> iterates and returns rows."""
        adapter = MockSolidWorksAdapter(
            {"mock_connect_delay": 0.0, "mock_model_delay": 0.0, "mock_feature_delay": 0.0}
        )
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        await adapter.create_extrusion(ExtrusionParameters(depth=10.0))
        result = await adapter.list_features()
        assert result.status == AdapterResultStatus.SUCCESS
        assert isinstance(result.data, list)
        assert len(result.data) >= 1

    @pytest.mark.asyncio
    async def test_list_features_include_suppressed_false_filters(self):
        """Lines 293-295: suppressed features excluded when include_suppressed=False."""
        adapter = MockSolidWorksAdapter(
            {"mock_connect_delay": 0.0, "mock_model_delay": 0.0, "mock_feature_delay": 0.0}
        )
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        # Add an extrusion and manually mark it suppressed
        await adapter.create_extrusion(ExtrusionParameters(depth=5.0))
        # Mark the feature as suppressed
        for feature in adapter._features.values():
            if feature.properties is None:
                feature.properties = {}
            feature.properties["suppressed"] = True

        result_no_suppressed = await adapter.list_features(include_suppressed=False)
        result_with_suppressed = await adapter.list_features(include_suppressed=True)

        assert result_no_suppressed.status == AdapterResultStatus.SUCCESS
        assert result_with_suppressed.status == AdapterResultStatus.SUCCESS
        # Without suppressed: zero features returned; with: at least one
        assert len(result_no_suppressed.data) == 0
        assert len(result_with_suppressed.data) >= 1


class TestMockAdapterListConfigurations:
    """Covers list_configurations non-Default active config (lines 311-317)."""

    @pytest.mark.asyncio
    async def test_list_configurations_default_config(self):
        """Active config == 'Default' -> returns ['Default']."""
        adapter = MockSolidWorksAdapter({"mock_connect_delay": 0.0, "mock_model_delay": 0.0})
        await adapter.connect()
        await adapter.create_part()
        result = await adapter.list_configurations()
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data == ["Default"]

    @pytest.mark.asyncio
    async def test_list_configurations_non_default_config(self):
        """Lines 315: non-Default config -> ['Default', active_config]."""
        adapter = MockSolidWorksAdapter({"mock_connect_delay": 0.0, "mock_model_delay": 0.0})
        await adapter.connect()
        await adapter.create_part()
        # Override current model's configuration to a non-default value
        adapter._current_model.configuration = "LightWeight"
        result = await adapter.list_configurations()
        assert result.status == AdapterResultStatus.SUCCESS
        assert "Default" in result.data
        assert "LightWeight" in result.data


class TestMockAdapterAddCenterline:
    """Covers add_centerline success path (lines 662-667)."""

    @pytest.mark.asyncio
    async def test_add_centerline_with_active_sketch(self):
        """Lines 662-667: add_centerline succeeds when sketch is active."""
        adapter = MockSolidWorksAdapter(
            {"mock_connect_delay": 0.0, "mock_sketch_delay": 0.0}
        )
        await adapter.connect()
        await adapter.create_sketch("Front")
        result = await adapter.add_centerline(0.0, 0.0, 10.0, 0.0)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data is not None
        assert "Centerline" in result.data

    @pytest.mark.asyncio
    async def test_add_centerline_no_sketch_returns_error(self):
        """add_centerline without active sketch returns ERROR."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        result = await adapter.add_centerline(0.0, 0.0, 1.0, 1.0)
        assert result.status == AdapterResultStatus.ERROR


# ---------------------------------------------------------------------------
# 4. config.py
# ---------------------------------------------------------------------------

class TestSolidWorksMCPConfigValidators:
    """Covers set_cache_dir, set_log_file, validate_adapter_type, validate_port."""

    def test_set_cache_dir_none_defaults_to_data_dir_cache(self, tmp_path: Path):
        """Lines 246-251: cache_dir=None -> data_dir/cache."""
        cfg = SolidWorksMCPConfig(mock_solidworks=True, data_dir=tmp_path, cache_dir=None)
        assert cfg.cache_dir == tmp_path / "cache"

    def test_set_cache_dir_explicit_value_kept(self, tmp_path: Path):
        """Lines 252: explicit cache_dir is passed through unchanged."""
        explicit = tmp_path / "my_cache"
        cfg = SolidWorksMCPConfig(mock_solidworks=True, data_dir=tmp_path, cache_dir=explicit)
        assert cfg.cache_dir == explicit

    def test_set_log_file_none_defaults_to_data_dir_logs(self, tmp_path: Path):
        """Lines 258-263: log_file=None -> data_dir/logs/server.log."""
        cfg = SolidWorksMCPConfig(mock_solidworks=True, data_dir=tmp_path, log_file=None)
        assert cfg.log_file == tmp_path / "logs" / "server.log"

    def test_set_log_file_explicit_value_kept(self, tmp_path: Path):
        """Lines 264: explicit log_file is passed through unchanged."""
        explicit = tmp_path / "custom.log"
        cfg = SolidWorksMCPConfig(mock_solidworks=True, data_dir=tmp_path, log_file=explicit)
        assert cfg.log_file == explicit

    def test_validate_adapter_type_passthrough(self, tmp_path: Path):
        """Line 328: validate_adapter_type returns the value unchanged."""
        cfg = SolidWorksMCPConfig(
            mock_solidworks=True, data_dir=tmp_path, adapter_type=AdapterType.MOCK
        )
        assert cfg.adapter_type == AdapterType.MOCK

    def test_validate_port_valid(self, tmp_path: Path):
        """Port within valid range is accepted."""
        cfg = SolidWorksMCPConfig(mock_solidworks=True, data_dir=tmp_path, port=8080)
        assert cfg.port == 8080

    def test_validate_port_too_low_raises(self, tmp_path: Path):
        """Lines 336-337: port < 1 raises ValueError."""
        with pytest.raises(Exception):
            SolidWorksMCPConfig(mock_solidworks=True, data_dir=tmp_path, port=0)

    def test_validate_port_too_high_raises(self, tmp_path: Path):
        """Lines 336-338: port > 65535 raises ValueError."""
        with pytest.raises(Exception):
            SolidWorksMCPConfig(mock_solidworks=True, data_dir=tmp_path, port=65536)


class TestLoadConfig:
    """Covers load_config() with no args (line 417)."""

    def test_load_config_no_args_returns_config(self, tmp_path: Path, monkeypatch):
        """Line 417: load_config() with no args calls SolidWorksMCPConfig.from_env()."""
        # Ensure no SOLIDWORKS_MCP_ env vars interfere
        monkeypatch.delenv("SOLIDWORKS_MCP_PORT", raising=False)
        cfg = load_config()
        assert isinstance(cfg, SolidWorksMCPConfig)

    def test_load_config_with_json_file(self, tmp_path: Path):
        """load_config() with a JSON file path reads and constructs config."""
        import json

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"mock_solidworks": True, "port": 9123, "data_dir": str(tmp_path)}),
            encoding="utf-8",
        )
        cfg = load_config(str(config_file))
        assert cfg.port == 9123


# ---------------------------------------------------------------------------
# 5. __init__.py
# ---------------------------------------------------------------------------

class TestPackageInit:
    """Covers __getattr__ lazy loader (lines 40-46) and __dir__ (line 58)."""

    def test_lazy_load_create_server(self):
        """Lines 40-46: accessing create_server triggers lazy import."""
        import src.solidworks_mcp as sw_module

        fn = sw_module.create_server
        assert callable(fn)

    def test_lazy_load_main(self):
        """Lines 40-46: accessing main triggers lazy import."""
        import src.solidworks_mcp as sw_module

        fn = sw_module.main
        assert callable(fn)

    def test_getattr_invalid_name_raises_attribute_error(self):
        """Line 48: unknown attribute raises AttributeError."""
        import src.solidworks_mcp as sw_module

        with pytest.raises(AttributeError):
            _ = sw_module.nonexistent_symbol_xyz

    def test_dir_includes_all_exports(self):
        """Line 58: dir() returns all declared public names."""
        import src.solidworks_mcp as sw_module

        d = dir(sw_module)
        assert "create_server" in d
        assert "main" in d
        assert "__version__" in d
        assert "SolidWorksMCPConfig" in d
