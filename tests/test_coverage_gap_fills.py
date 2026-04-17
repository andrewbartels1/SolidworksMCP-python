"""
Coverage gap-fill tests targeting specific missed lines across multiple modules.

Targets:
- adapters/vba_adapter.py: lines 47, 51, 55, 59-64, 102, 114, 172, 224
- adapters/vba_macro_executor.py: lines 111-122, 142, 186, 197, 199-200
- cache/response_cache.py: lines 81, 89-90, 102, 112, 117-123, 138-139
- security/runtime.py: lines 56, 65, 96, 102, 105, 110
- security/cors.py: line 23
- adapters/circuit_breaker.py: lines 187, 226, 243, 279
- adapters/base.py: lines 425, 438
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from src.solidworks_mcp.adapters.base import (
    AdapterResultStatus,
    LoftParameters,
    SweepParameters,
)
from src.solidworks_mcp.adapters.circuit_breaker import (
    CircuitBreakerAdapter,
    CircuitState,
)
from src.solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from src.solidworks_mcp.adapters.vba_adapter import VbaGeneratorAdapter
from src.solidworks_mcp.adapters.vba_macro_executor import (
    MacroExecutionRequest,
    VbaMacroExecutor,
)
from src.solidworks_mcp.cache.response_cache import CachePolicy, ResponseCache
from src.solidworks_mcp.config import SecurityLevel, SolidWorksMCPConfig
from src.solidworks_mcp.security import cors as cors_mod
from src.solidworks_mcp.security.runtime import SecurityEnforcer, SecurityError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RaisingAdapter:
    """Backing adapter whose execute_macro raises RuntimeError (not AttributeError)."""

    async def execute_macro(self, macro_path: str, subroutine: str) -> None:
        raise RuntimeError("simulated COM failure")


class _AttrErrorAdapter:
    """Backing adapter whose execute_macro raises AttributeError."""

    async def execute_macro(self, macro_path: str, subroutine: str) -> None:
        raise AttributeError("mocked attribute error")


class _NoMacroAdapter:
    """Backing adapter with no execute_macro attribute at all."""


# ===========================================================================
# vba_adapter.py gaps: lines 47, 51, 55, 59-64, 102, 114, 172, 224
# ===========================================================================


@pytest.mark.asyncio
async def test_vba_adapter_connect_disconnect_is_connected() -> None:
    """Lines 47, 51, 55 — connect/disconnect/is_connected delegate to backing."""
    backing = MockSolidWorksAdapter({})
    adapter = VbaGeneratorAdapter(backing_adapter=backing)

    await adapter.connect()  # line 47
    assert adapter.is_connected()  # line 55
    await adapter.disconnect()  # line 51


@pytest.mark.asyncio
async def test_vba_adapter_health_check_adds_vba_route_marker() -> None:
    """Lines 59-64 — health_check merges metrics with route=vba."""
    backing = MockSolidWorksAdapter({})
    adapter = VbaGeneratorAdapter(backing_adapter=backing)

    health = await adapter.health_check()
    assert health.metrics is not None
    assert health.metrics.get("route") == "vba"


@pytest.mark.asyncio
async def test_vba_adapter_create_sweep_and_loft() -> None:
    """Lines 102, 114, 172 — create_sweep body + _generate_sweep_vba + create_loft body."""
    backing = MockSolidWorksAdapter({})
    adapter = VbaGeneratorAdapter(backing_adapter=backing)

    # create_sweep (line 102) calls _generate_sweep_vba (line 172)
    sweep_result = await adapter.create_sweep(SweepParameters(path="Edge<1>"))
    assert sweep_result is not None

    # create_loft (line 114) calls _generate_loft_vba
    loft_result = await adapter.create_loft(
        LoftParameters(profiles=["Profile1", "Profile2"])
    )
    assert loft_result is not None


@pytest.mark.asyncio
async def test_vba_adapter_execute_macro_delegation() -> None:
    """Line 224 — execute_macro delegates to _macro_executor."""
    backing = MockSolidWorksAdapter({})
    adapter = VbaGeneratorAdapter(backing_adapter=backing)

    result = await adapter.execute_macro(
        macro_code="Sub Main()\nEnd Sub",
        macro_name="GapTestMacro",
        subroutine="Main",
    )
    assert result is not None


# ===========================================================================
# vba_macro_executor.py gaps: lines 111-122, 142, 186, 197, 199-200
# ===========================================================================


@pytest.mark.asyncio
async def test_vba_macro_executor_exception_handler() -> None:
    """Lines 111-122 — except block in execute_macro when adapter raises RuntimeError."""
    executor = VbaMacroExecutor()
    request = MacroExecutionRequest(
        macro_code="Sub Main()\nEnd Sub",
        macro_name="FailMacro",
        subroutine="Main",
    )
    result = await executor.execute_macro(
        request=request,
        backing_adapter=_RaisingAdapter(),
    )
    assert result.status == AdapterResultStatus.ERROR
    # History should contain the failed entry
    hist = executor.get_execution_history()
    assert "FailMacro" in hist
    assert hist["FailMacro"].success is False


@pytest.mark.asyncio
async def test_vba_macro_executor_get_history_by_name() -> None:
    """Line 142 — get_execution_history(macro_name=...) with existing entry."""
    executor = VbaMacroExecutor()
    backing = MockSolidWorksAdapter({})
    request = MacroExecutionRequest(
        macro_code="Sub NamedMac()\nEnd Sub",
        macro_name="NamedMacro",
        subroutine="NamedMac",
    )
    await executor.execute_macro(request=request, backing_adapter=backing)

    # Fetch with specific name — covers the conditional return branch
    specific = executor.get_execution_history("NamedMacro")
    assert "NamedMacro" in specific

    # Fetch a name that was never run — returns empty dict
    missing = executor.get_execution_history("Ghost")
    assert missing == {}


@pytest.mark.asyncio
async def test_vba_macro_executor_no_execute_macro_on_adapter() -> None:
    """Line 186 — _execute_via_adapter returns error when adapter lacks execute_macro."""
    executor = VbaMacroExecutor()
    request = MacroExecutionRequest(
        macro_code="Sub Main()\nEnd Sub",
        macro_name="NoExecMacro",
    )
    result = await executor.execute_macro(
        request=request,
        backing_adapter=_NoMacroAdapter(),
    )
    # The "no execute_macro" path returns success=False, not an exception
    assert result is not None
    hist = executor.get_execution_history("NoExecMacro")
    assert hist["NoExecMacro"].success is False


@pytest.mark.asyncio
async def test_vba_macro_executor_attribute_error_in_adapter() -> None:
    """Lines 197, 199-200 — AttributeError caught inside _execute_via_adapter."""
    executor = VbaMacroExecutor()
    request = MacroExecutionRequest(
        macro_code="Sub Main()\nEnd Sub",
        macro_name="AttrErrMacro",
    )
    result = await executor.execute_macro(
        request=request,
        backing_adapter=_AttrErrorAdapter(),
    )
    # AttributeError is caught in _execute_via_adapter; outer call sees success
    assert result is not None
    hist = executor.get_execution_history("AttrErrMacro")
    assert hist["AttrErrMacro"].success is False


# ===========================================================================
# cache/response_cache.py gaps: 81, 89-90, 102, 112, 117-123, 138-139
# ===========================================================================


def test_cache_get_disabled_returns_none() -> None:
    """Line 81 — disabled cache.get() returns None immediately."""
    cache = ResponseCache(CachePolicy(enabled=False))
    key = cache.make_key("op", {})
    assert cache.get(key) is None


def test_cache_get_expired_entry_evicted() -> None:
    """Lines 89-90 — expired entry is removed and None returned."""
    cache = ResponseCache(CachePolicy(enabled=True, default_ttl_seconds=60))
    key = cache.make_key("get_model_info", {"x": 1})
    cache.set(key, "stale_value")

    # Forcibly expire the entry
    with cache._lock:
        entry = cache._entries[key]
        entry.expires_at = time.time() - 1.0  # already expired

    result = cache.get(key)
    assert result is None
    # Entry should have been popped
    assert key not in cache._entries


def test_cache_set_disabled_does_nothing() -> None:
    """Line 102 — disabled cache.set() returns without storing."""
    cache = ResponseCache(CachePolicy(enabled=False))
    key = cache.make_key("op", {})
    cache.set(key, "some_value")
    assert len(cache._entries) == 0


def test_cache_set_max_entries_evicts_oldest() -> None:
    """Lines 112, 117-123 — set() triggers _evict_oldest_unlocked when full."""
    cache = ResponseCache(CachePolicy(enabled=True, max_entries=2))
    k1 = cache.make_key("op", {"n": 1})
    k2 = cache.make_key("op", {"n": 2})
    k3 = cache.make_key("op", {"n": 3})

    cache.set(k1, "v1")
    cache.set(k2, "v2")
    assert len(cache._entries) == 2

    cache.set(k3, "v3")  # triggers eviction — covers lines 112, 117-123
    assert len(cache._entries) == 2


def test_cache_normalize_payload_fallback_for_nan() -> None:
    """Lines 138-139 — _normalize_payload except branch for JSON-incompatible value."""
    cache = ResponseCache(CachePolicy(enabled=True))
    # float("nan") causes json.dumps to raise ValueError (out-of-range float)
    key = cache.make_key("op", float("nan"))
    assert isinstance(key, str)
    assert len(key) == 64  # SHA-256 hex digest length


# ===========================================================================
# security/runtime.py gaps: 56, 65, 96, 102, 105, 110
# ===========================================================================


def test_security_enforcer_rate_limit_exceeded() -> None:
    """Line 56 — SecurityError raised when rate limit is exceeded."""
    config = SolidWorksMCPConfig(
        mock_solidworks=True,
        enable_rate_limiting=True,
        api_key_required=False,
    )
    enforcer = SecurityEnforcer(config)

    # Exhaust the rate limit by monkeypatching check_rate_limit to False
    import src.solidworks_mcp.security.runtime as runtime_mod

    original = runtime_mod.check_rate_limit
    try:
        runtime_mod.check_rate_limit = lambda client_id: False
        with pytest.raises(SecurityError, match="rate limit exceeded"):
            enforcer.enforce(tool_name="create_part", payload={"client_id": "tester"})
    finally:
        runtime_mod.check_rate_limit = original


def test_security_enforcer_auth_not_required_returns_early() -> None:
    """Line 65 — enforce() returns without checking API key when auth not required."""
    config = SolidWorksMCPConfig(
        mock_solidworks=True,
        enable_rate_limiting=False,
        api_key_required=False,
        security_level=SecurityLevel.MINIMAL,
        # no api_key, no api_keys
    )
    enforcer = SecurityEnforcer(config)

    # Should NOT raise — auth is not required
    enforcer.enforce(tool_name="create_part", payload={})


def test_security_enforcer_api_key_required_but_none_configured() -> None:
    """Lines 61, 68 (security enforcer) — api_key_required but no key configured raises."""
    config = SolidWorksMCPConfig(
        mock_solidworks=True,
        enable_rate_limiting=False,
        api_key_required=True,
        # no api_key, no api_keys set
    )
    enforcer = SecurityEnforcer(config)

    with pytest.raises(SecurityError, match="no API key configured"):
        enforcer.enforce(tool_name="create_part", payload={"api_key": "anything"})


def test_security_enforcer_strict_level_api_keys_list() -> None:
    """Lines 96, 102, 105, 110 — STRICT level + api_keys list path."""
    config = SolidWorksMCPConfig(
        mock_solidworks=True,
        enable_rate_limiting=False,
        security_level=SecurityLevel.STRICT,
        api_key_required=False,
        api_keys=["correct-key"],
    )
    enforcer = SecurityEnforcer(config)

    # Line 96: api_key_required=False, but STRICT → _is_auth_required returns True
    # Line 110: api_keys[0] used as expected key
    # No key provided → line 102 (key not provided) raises
    with pytest.raises(SecurityError, match="api_key was not provided"):
        enforcer.enforce(tool_name="create_part", payload={})

    # Wrong key → line 105 (invalid key) raises
    with pytest.raises(SecurityError, match="invalid api_key"):
        enforcer.enforce(tool_name="create_part", payload={"api_key": "wrong"})

    # Correct key → succeeds
    enforcer.enforce(tool_name="create_part", payload={"api_key": "correct-key"})


# ===========================================================================
# security/cors.py gap: line 23
# ===========================================================================


def test_setup_cors_handles_object_without_dict() -> None:
    """Line 23 — AttributeError/TypeError when setattr fails on plain object()."""
    cfg = SimpleNamespace(cors_origins=[], allowed_origins=[], enable_cors=True)
    # object() does not allow attribute assignment — triggers except branch
    cors_mod.setup_cors(object(), cfg)  # should not raise


# ===========================================================================
# adapters/circuit_breaker.py gaps: 187, 226, 243, 279
# ===========================================================================


@pytest.mark.asyncio
async def test_circuit_breaker_connect_failure_records_failure() -> None:
    """Line 187 — _record_failure() called when connect() raises."""
    mock = MockSolidWorksAdapter({})

    async def _raise_on_connect() -> None:
        raise RuntimeError("connect failed")

    mock.connect = _raise_on_connect  # type: ignore[method-assign]

    adapter = CircuitBreakerAdapter(adapter=mock)
    assert adapter.failure_count == 0

    with pytest.raises(RuntimeError):
        await adapter.connect()  # raises → calls _record_failure (line 187)

    assert adapter.failure_count == 1


@pytest.mark.asyncio
async def test_circuit_breaker_health_check_open_state() -> None:
    """Line 226 — health_check marks healthy=False when circuit is OPEN."""
    adapter = CircuitBreakerAdapter(adapter=MockSolidWorksAdapter({}))
    # Force circuit into OPEN state
    adapter.state = CircuitState.OPEN

    health = await adapter.health_check()
    assert health.healthy is False
    assert health.connection_status == "circuit_breaker_open"
    assert health.metrics["circuit_breaker"]["state"] == "open"


@pytest.mark.asyncio
async def test_circuit_breaker_call_raises_when_open() -> None:
    """Line 243 — call() raises when circuit is OPEN."""
    adapter = CircuitBreakerAdapter(adapter=MockSolidWorksAdapter({}))
    adapter.state = CircuitState.OPEN
    # Ensure recovery timeout has not elapsed
    adapter.last_failure_time = time.time()

    with pytest.raises(Exception, match="Circuit breaker is open"):
        await adapter.call(lambda: None)


@pytest.mark.asyncio
async def test_circuit_breaker_call_records_failure_on_exception() -> None:
    """Line 279 — call() calls _record_failure when operation raises."""
    adapter = CircuitBreakerAdapter(adapter=MockSolidWorksAdapter({}))

    async def _bad_op() -> None:
        raise RuntimeError("op failed")

    with pytest.raises(RuntimeError):
        await adapter.call(_bad_op)

    assert adapter.failure_count == 1


# ===========================================================================
# adapters/base.py gaps: lines 425, 438 (add_arc, add_spline default impls)
# ===========================================================================


@pytest.mark.asyncio
async def test_base_adapter_default_add_arc_and_add_spline() -> None:
    """Lines 425, 438 — default add_arc/add_spline return NOT_IMPLEMENTED errors."""
    adapter = MockSolidWorksAdapter({})

    arc_result = await adapter.add_arc(0, 0, 1, 0, 0, 1)
    assert arc_result.status == AdapterResultStatus.ERROR
    assert "add_arc" in (arc_result.error or "")

    spline_result = await adapter.add_spline([{"x": 0, "y": 0}, {"x": 1, "y": 1}])
    assert spline_result.status == AdapterResultStatus.ERROR
    assert "add_spline" in (spline_result.error or "")
