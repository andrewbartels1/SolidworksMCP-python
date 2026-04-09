"""Tests for runtime architecture features: analyzer, router, cache, VBA, and security."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.solidworks_mcp.adapters.base import (
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
    RevolveParameters,
)
from src.solidworks_mcp.adapters.complexity_analyzer import ComplexityAnalyzer
from src.solidworks_mcp.adapters.intelligent_router import IntelligentRouter
from src.solidworks_mcp.adapters.vba_adapter import VbaGeneratorAdapter
from src.solidworks_mcp.cache.response_cache import CachePolicy, ResponseCache
from src.solidworks_mcp.config import SecurityLevel, SolidWorksMCPConfig
from src.solidworks_mcp.security.runtime import SecurityEnforcer, SecurityError
from src.solidworks_mcp.adapters.vba_macro_executor import (
    MacroExecutionRequest,
    VbaMacroExecutor,
)
from src.solidworks_mcp.server import SolidWorksMCPServer


class _BackingAdapter:
    """Minimal backing adapter used to test VBA wrapper behavior."""

    def __init__(self) -> None:
        self.config = {"name": "backing"}

    async def connect(self) -> None:
        """Connect mock."""

    async def disconnect(self) -> None:
        """Disconnect mock."""

    def is_connected(self) -> bool:
        """Return mock connection state."""
        return True

    async def health_check(self) -> SimpleNamespace:
        """Return health-like object with mutable metrics."""
        return SimpleNamespace(metrics={"adapter": "mock"})

    async def create_extrusion(
        self,
        params: ExtrusionParameters,
    ) -> AdapterResult[dict[str, str]]:
        """Return successful extrusion result."""
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={"feature": "extrusion"},
        )

    async def create_revolve(
        self,
        params: RevolveParameters,
    ) -> AdapterResult[dict[str, str]]:
        """Return successful revolve result."""
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={"feature": "revolve"},
        )

    async def get_model_info(self) -> AdapterResult[dict[str, str]]:
        """Return lightweight model information payload."""
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={"name": "part"},
        )


def test_response_cache_set_get_and_key_determinism() -> None:
    """Cache should return values and key generation should be deterministic."""
    cache = ResponseCache(
        CachePolicy(enabled=True, default_ttl_seconds=60, max_entries=4)
    )

    payload = {"a": 1, "b": [2, 3]}
    key1 = cache.make_key("get_model_info", payload)
    key2 = cache.make_key("get_model_info", payload)

    assert key1 == key2
    assert cache.get(key1) is None

    cache.set(key1, {"status": "ok"})
    assert cache.get(key1) == {"status": "ok"}


def test_complexity_analyzer_prefers_vba_for_complex_payloads() -> None:
    """Analyzer should prefer VBA for high-parameter extrusion payloads."""
    analyzer = ComplexityAnalyzer(parameter_threshold=4, score_threshold=0.5)

    decision = analyzer.analyze(
        operation="create_extrusion",
        payload={"a": 1, "b": 2, "c": 3, "d": 4, "e": 5},
    )

    assert decision.prefer_vba is True
    assert decision.parameter_count >= 5
    assert decision.complexity_score > 0


@pytest.mark.asyncio
async def test_intelligent_router_uses_vba_when_preferred() -> None:
    """Router should execute VBA route when complexity recommends it."""
    analyzer = ComplexityAnalyzer(parameter_threshold=2, score_threshold=0.4)
    cache = ResponseCache(
        CachePolicy(enabled=True, default_ttl_seconds=60, max_entries=8)
    )
    router = IntelligentRouter(analyzer=analyzer, cache=cache)

    async def _com(payload: object) -> AdapterResult[dict[str, str]]:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="com failed")

    async def _vba(payload: object) -> AdapterResult[dict[str, str]]:
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data={"route": "vba"})

    result, route = await router.execute(
        operation="create_extrusion",
        payload={"one": 1, "two": 2, "three": 3},
        call_args=({"one": 1, "two": 2, "three": 3},),
        call_kwargs={},
        com_operation=_com,
        vba_operation=_vba,
    )

    assert result.is_success is True
    assert route.route == "vba"


@pytest.mark.asyncio
async def test_vba_adapter_adds_route_metadata() -> None:
    """VBA wrapper should annotate results with VBA metadata."""
    adapter = VbaGeneratorAdapter(backing_adapter=_BackingAdapter())
    result = await adapter.create_extrusion(ExtrusionParameters(depth=10.0))

    assert result.is_success is True
    assert result.metadata is not None
    assert result.metadata.get("route") == "vba"
    assert "vba_code" in result.metadata


def test_security_enforcer_requires_valid_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Security enforcer should reject missing or invalid API keys in strict mode."""
    config = SolidWorksMCPConfig(
        security_level=SecurityLevel.STRICT,
        api_keys=["expected-key"],
        api_key_required=True,
        mock_solidworks=True,
        enable_rate_limiting=True,
    )
    enforcer = SecurityEnforcer(config)

    monkeypatch.setattr(
        "src.solidworks_mcp.security.runtime.check_rate_limit",
        lambda client_id: True,
    )

    with pytest.raises(SecurityError):
        enforcer.enforce(tool_name="create_part", payload={"client_id": "u1"})

    with pytest.raises(SecurityError):
        enforcer.enforce(
            tool_name="create_part",
            payload={"client_id": "u1", "api_key": "wrong"},
        )

    enforcer.enforce(
        tool_name="create_part",
        payload={"client_id": "u1", "api_key": "expected-key"},
    )


@pytest.mark.asyncio
async def test_server_runtime_instrumentation_caches_read_calls() -> None:
    """Server instrumentation should cache eligible read operations."""
    cfg = SolidWorksMCPConfig(
        mock_solidworks=True,
        enable_intelligent_routing=True,
        enable_response_cache=True,
        response_cache_ttl_seconds=60,
    )
    server = SolidWorksMCPServer(cfg)

    class _AdapterWithCounter(_BackingAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def get_model_info(self) -> AdapterResult[dict[str, str]]:
            self.calls += 1
            return await super().get_model_info()

    adapter = _AdapterWithCounter()
    server.adapter = adapter
    server._configure_runtime_services()

    first = await server.adapter.get_model_info()
    second = await server.adapter.get_model_info()

    assert first.is_success is True
    assert second.is_success is True
    assert adapter.calls == 1


def test_complexity_analyzer_recognizes_expanded_operations() -> None:
    """Analyzer should know about all expanded operation profiles."""
    analyzer = ComplexityAnalyzer(parameter_threshold=12, score_threshold=0.6)

    # Test modeling operations
    decision = analyzer.analyze(
        operation="create_sweep",
        payload={"a": 1, "b": 2},
    )
    assert decision.operation == "create_sweep"
    assert decision.complexity_score >= 0

    # Test sketching operations
    decision = analyzer.analyze(
        operation="add_spline",
        payload={"points": [1, 2, 3, 4, 5]},
    )
    assert decision.operation == "add_spline"

    # Test assembly operations
    decision = analyzer.analyze(
        operation="add_mate",
        payload={"comp1": "a", "comp2": "b", "type": "coincident"},
    )
    assert decision.operation == "add_mate"


@pytest.mark.asyncio
async def test_intelligent_router_caches_more_operations() -> None:
    """Router should cache all operations in expanded cacheable set."""
    analyzer = ComplexityAnalyzer()
    cache = ResponseCache(CachePolicy(enabled=True, default_ttl_seconds=60))
    expanded_cacheable = {
        "get_model_info",
        "get_mass_properties",
        "analyze_drawing_dimensions",
        "check_drawing_compliance",
    }
    router = IntelligentRouter(
        analyzer=analyzer,
        cache=cache,
        cacheable_operations=expanded_cacheable,
    )

    call_count = {"count": 0}

    async def _com_operation(payload: object) -> AdapterResult[dict[str, str]]:
        call_count["count"] += 1
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data={"cached": False})

    payload = {"model": "test"}

    result1, _ = await router.execute(
        operation="get_mass_properties",
        payload=payload,
        call_args=(payload,),
        call_kwargs={},
        com_operation=_com_operation,
        vba_operation=None,
    )

    result2, route2 = await router.execute(
        operation="get_mass_properties",
        payload=payload,
        call_args=(payload,),
        call_kwargs={},
        com_operation=_com_operation,
        vba_operation=None,
    )

    assert result1.is_success is True
    assert result2.is_success is True
    assert route2.used_cache is True
    assert call_count["count"] == 1


@pytest.mark.asyncio
async def test_vba_macro_executor_saves_and_executes_macro() -> None:
    """VBA executor should save macro to disk and execute via adapter."""
    executor = VbaMacroExecutor()

    request = MacroExecutionRequest(
        macro_code="Sub Main()\nEnd Sub",
        macro_name="test_macro",
        subroutine="Main",
    )

    class _MockAdapter:
        async def execute_macro(
            self, macro_path: str, subroutine: str
        ) -> dict[
            str,
            str,
        ]:
            return {"success": True, "output": "macro executed"}

    result = await executor.execute_macro(
        request=request,
        backing_adapter=_MockAdapter(),
    )

    assert result.is_success is True
    assert result.data is not None
    assert result.data.success is True
    assert result.metadata is not None
    assert "macro_path" in result.metadata


@pytest.mark.asyncio
async def test_vba_adapter_executes_generated_macro() -> None:
    """VBA adapter should execute generated macros through executor."""

    class _MockBackingAdapter(_BackingAdapter):
        async def execute_macro(
            self, macro_path: str, subroutine: str
        ) -> dict[
            str,
            str,
        ]:
            return {"success": True, "output": "done"}

    adapter = VbaGeneratorAdapter(backing_adapter=_MockBackingAdapter())
    result = await adapter.execute_macro(
        macro_code="Sub Main()\nEnd Sub",
        macro_name="test",
    )

    assert result.is_success is True


def test_vba_adapter_tracks_execution_history() -> None:
    """VBA adapter should maintain execution history."""

    class _MockBackingAdapter(_BackingAdapter):
        async def execute_macro(
            self, macro_path: str, subroutine: str
        ) -> dict[
            str,
            str,
        ]:
            return {"success": True}

    adapter = VbaGeneratorAdapter(backing_adapter=_MockBackingAdapter())
    history = adapter.get_macro_execution_history()

    assert isinstance(history, dict)
