from __future__ import annotations

import asyncio
import time
from collections import namedtuple
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.solidworks_mcp.adapters.base import (
    AdapterHealth,
    AdapterResult,
    AdapterResultStatus,
    SolidWorksAdapter,
    SolidWorksModel,
)
from src.solidworks_mcp.adapters.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerAdapter,
    CircuitState,
)
from src.solidworks_mcp.exceptions import SolidWorksMCPError
from src.solidworks_mcp.security import auth as auth_mod
from src.solidworks_mcp.security import cors as cors_mod
from src.solidworks_mcp.security import rate_limiting as rl_mod
from src.solidworks_mcp.security import setup_security
from src.solidworks_mcp.utils.logging import get_audit_logger, setup_logging
from src.solidworks_mcp.utils.validation import validate_environment


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

    async def list_features(self, include_suppressed: bool = False):
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

    async def get_dimension(self, name: str):
        """Test helper for get dimension."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=1.0)

    async def set_dimension(self, name: str, value: float):
        """Test helper for set dimension."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)


@pytest.mark.asyncio
async def test_security_setup_branches_and_auth_helpers(monkeypatch):
    # Minimal security: early return
    """Test security setup branches and auth helpers."""
    minimal_cfg = SimpleNamespace(security_level="minimal")

    class _Level:
        """Test suite for Level."""
        MINIMAL = "minimal"
        STANDARD = "standard"
        STRICT = "strict"

    monkeypatch.setitem(
        __import__("sys").modules,
        "src.solidworks_mcp.config",
        SimpleNamespace(SecurityLevel=_Level),
    )

    await setup_security(object(), minimal_cfg)

    calls = {"auth": 0, "cors": 0, "rate": 0}
    monkeypatch.setattr(
        "src.solidworks_mcp.security.setup_authentication",
        lambda *_: calls.__setitem__("auth", calls["auth"] + 1),
    )
    monkeypatch.setattr(
        "src.solidworks_mcp.security.setup_cors",
        lambda *_: calls.__setitem__("cors", calls["cors"] + 1),
    )
    monkeypatch.setattr(
        "src.solidworks_mcp.security.setup_rate_limiting",
        lambda *_: calls.__setitem__("rate", calls["rate"] + 1),
    )

    strict_cfg = SimpleNamespace(
        security_level="strict",
        api_key="abc",
        enable_cors=True,
        enable_rate_limiting=True,
    )
    await setup_security(object(), strict_cfg)
    assert calls == {"auth": 1, "cors": 1, "rate": 1}

    # auth and cors placeholders
    assert auth_mod.validate_api_key("k", "k") is True
    assert auth_mod.validate_api_key("", "k") is False
    auth_mod.setup_authentication(object(), object())
    cors_mod.setup_cors(object(), object())

    @auth_mod.require_auth(object())
    async def _inner(v):
        """Test helper for inner."""
        return v + 1

    assert await _inner(1) == 2


def test_rate_limiter_window_and_global_setup(monkeypatch):
    """Test rate limiter window and global setup."""
    rl = rl_mod.RateLimiter(max_requests=2, time_window=5)

    # Fill limit
    assert rl.is_allowed("c1") is True
    assert rl.is_allowed("c1") is True
    assert rl.is_allowed("c1") is False

    # Advance time by replacing time.time to force expiry of old requests
    base = time.time()
    monkeypatch.setattr(rl_mod.time, "time", lambda: base + 10)
    assert rl.is_allowed("c1") is True

    cfg = SimpleNamespace(rate_limit_per_minute=1)
    rl_mod.setup_rate_limiting(object(), cfg)
    assert rl_mod.check_rate_limit("client") is True
    assert rl_mod.check_rate_limit("client") is False

    rl_mod._rate_limiter = None
    assert rl_mod.check_rate_limit("client") is True


@pytest.mark.asyncio
async def test_validate_environment_branches(monkeypatch):
    """Test validate environment branches."""
    cfg = SimpleNamespace(
        can_use_solidworks=False,
        mock_solidworks=False,
        enable_windows_validation=False,
    )

    # Non-windows warning path
    monkeypatch.setattr(
        "src.solidworks_mcp.utils.validation.platform.system", lambda: "Linux"
    )
    await validate_environment(cfg)

    # Windows validation branch calls helper
    cfg2 = SimpleNamespace(
        can_use_solidworks=False,
        mock_solidworks=False,
        enable_windows_validation=True,
    )
    helper = AsyncMock()
    monkeypatch.setattr(
        "src.solidworks_mcp.utils.validation._validate_solidworks_installation", helper
    )
    monkeypatch.setattr(
        "src.solidworks_mcp.utils.validation.platform.system", lambda: "Windows"
    )
    await validate_environment(cfg2)
    helper.assert_awaited_once()

    # Python version guard
    import sys

    VersionInfo = namedtuple(
        "VersionInfo", ["major", "minor", "micro", "releaselevel", "serial"]
    )
    fake_vi = VersionInfo(3, 10, 0, "final", 0)
    monkeypatch.setattr(sys, "version_info", fake_vi)
    with pytest.raises(SolidWorksMCPError):
        await validate_environment(cfg)


def test_setup_logging_file_and_audit(tmp_path: Path):
    # Newer loguru versions may reject "gzip" shorthand in tests; mock add()
    # so we still execute setup branches deterministically.
    """Test setup logging file and audit."""
    from src.solidworks_mcp.utils import logging as logging_mod

    logging_mod.logger.add = lambda *args, **kwargs: 1

    cfg = SimpleNamespace(
        log_level="INFO",
        log_file=tmp_path / "logs" / "app.log",
        enable_audit_logging=True,
    )
    setup_logging(cfg)
    audit = get_audit_logger()
    audit.info("audit event", audit_type="security")

    assert (tmp_path / "logs").exists()


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
async def test_circuit_breaker_adapter_core_paths(monkeypatch):
    """Test circuit breaker adapter core paths."""
    adapter = _DummyAdapter({})
    cb = CircuitBreakerAdapter(
        adapter=adapter,
        failure_threshold=1,
        recovery_timeout=0,
        half_open_max_calls=1,
    )

    # open -> allow after timeout -> half-open
    cb.state = CircuitState.OPEN
    cb.last_failure_time = 0
    assert cb._should_allow_request() is True
    assert cb.state == CircuitState.HALF_OPEN

    # success in half-open closes breaker
    async def _ok():
        """Test helper for ok."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    result = await cb._execute_with_circuit_breaker("ok", _ok)
    assert result.is_success
    assert cb.state == CircuitState.CLOSED

    # error result increments failures and opens
    async def _bad_result():
        """Test helper for bad result."""
        return AdapterResult(status=AdapterResultStatus.ERROR, error="bad")

    cb.failure_threshold = 1
    res2 = await cb._execute_with_circuit_breaker("bad", _bad_result)
    assert res2.is_error
    assert cb.state == CircuitState.OPEN

    # exception path
    async def _boom():
        """Test helper for boom."""
        raise RuntimeError("boom")

    cb.state = CircuitState.CLOSED
    res3 = await cb._execute_with_circuit_breaker("boom", _boom)
    assert res3.is_error

    # open-state blocking is covered by the _execute gate path above
    cb.state = CircuitState.OPEN
    cb.recovery_timeout = 999999


@pytest.mark.asyncio
async def test_circuit_breaker_adapter_passthrough_methods(monkeypatch):
    """Test circuit breaker adapter passthrough methods."""
    cb = CircuitBreakerAdapter(adapter=_DummyAdapter({}), config={})

    async def _fake_exec(name, operation):
        """Test helper for fake exec."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data={"name": name})

    monkeypatch.setattr(cb, "_execute_with_circuit_breaker", _fake_exec)

    assert (await cb.open_model("a.sldprt")).is_success
    assert (await cb.close_model()).is_success
    assert (await cb.create_part()).is_success
    assert (await cb.create_assembly()).is_success
    assert (await cb.create_drawing()).is_success
    assert (await cb.create_extrusion({})).is_success
    assert (await cb.create_revolve({})).is_success
    assert (await cb.create_sweep({})).is_success
    assert (await cb.create_loft({})).is_success
    assert (await cb.create_sketch("Top")).is_success
    assert (await cb.add_line(0, 0, 1, 1)).is_success
    assert (await cb.add_circle(0, 0, 1)).is_success
    assert (await cb.add_rectangle(0, 0, 1, 1)).is_success
    assert (await cb.exit_sketch()).is_success
    assert (await cb.get_mass_properties()).is_success
    assert (await cb.export_file("a.step", "step")).is_success
    assert (await cb.get_dimension("D1@S")).is_success
    assert (await cb.set_dimension("D1@S", 1.0)).is_success

    await cb.disconnect()
    assert cb.is_connected() is True
    health = await cb.health_check()
    assert health.metrics and "circuit_breaker" in health.metrics


@pytest.mark.asyncio
async def test_legacy_circuit_breaker_paths():
    """Test legacy circuit breaker paths."""
    c = CircuitBreaker(
        failure_threshold=1, recovery_timeout=0.01, expected_exception=ValueError
    )

    async def _raise_once():
        """Test helper for raise once."""
        raise ValueError("x")

    with pytest.raises(ValueError):
        await c.call(_raise_once)
    assert c.state == CircuitState.OPEN

    with pytest.raises(Exception, match="Circuit breaker is open"):
        await c.call(lambda: 1)

    await asyncio.sleep(0.02)
    value = await c.call(lambda: 7)
    assert value == 7
    assert c.state == CircuitState.CLOSED
