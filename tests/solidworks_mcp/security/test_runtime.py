"""Branch coverage tests for solidworks_mcp.security.runtime."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from solidworks_mcp.config import SecurityLevel
from solidworks_mcp.security.runtime import (
    SecurityContext,
    SecurityEnforcer,
    SecurityError,
    constant_time_equals,
)


def test_get_security_enforcer_returns_current_value(monkeypatch) -> None:
    import solidworks_mcp.security as security_mod

    sentinel = object()
    monkeypatch.setattr(security_mod, "_security_enforcer", sentinel)
    assert security_mod.get_security_enforcer() is sentinel


def test_constant_time_equals_helper() -> None:
    assert constant_time_equals("abc", "abc") is True
    assert constant_time_equals("abc", "abd") is False


def test_extract_context_variants() -> None:
    enforcer = SecurityEnforcer(SimpleNamespace())

    from_dict = enforcer._extract_context({"client_id": "  c1 ", "api_key": 123})
    from_model = enforcer._extract_context(
        SimpleNamespace(model_dump=lambda: {"client_id": "", "api_key": "k"})
    )
    from_other = enforcer._extract_context(object())

    assert from_dict == SecurityContext(client_id="c1", api_key="123")
    assert from_model == SecurityContext(client_id="anonymous", api_key="k")
    assert from_other == SecurityContext(client_id="anonymous", api_key=None)


def test_auth_requirement_and_expected_key_resolution() -> None:
    secret = SimpleNamespace(get_secret_value=lambda: "sekret")

    strict_cfg = SimpleNamespace(
        api_key_required=False,
        security_level=SecurityLevel.STRICT,
        api_key=None,
        api_keys=[],
    )
    api_key_cfg = SimpleNamespace(
        api_key_required=False, security_level=None, api_key=secret, api_keys=[]
    )
    list_cfg = SimpleNamespace(
        api_key_required=False, security_level=None, api_key=None, api_keys=["k1", "k2"]
    )
    none_cfg = SimpleNamespace(
        api_key_required=False, security_level=None, api_key=None, api_keys=[]
    )

    assert SecurityEnforcer(strict_cfg)._is_auth_required() is True
    assert SecurityEnforcer(api_key_cfg)._is_auth_required() is True
    assert SecurityEnforcer(list_cfg)._is_auth_required() is True
    assert SecurityEnforcer(none_cfg)._is_auth_required() is False

    assert SecurityEnforcer(api_key_cfg)._expected_api_key() == "sekret"
    assert SecurityEnforcer(list_cfg)._expected_api_key() == "k1"
    assert SecurityEnforcer(none_cfg)._expected_api_key() is None


def test_enforce_rate_limit_and_auth_branches(monkeypatch) -> None:
    cfg = SimpleNamespace(
        enable_rate_limiting=True,
        api_key_required=True,
        security_level=None,
        api_key="expected",
        api_keys=[],
    )
    enforcer = SecurityEnforcer(cfg)

    monkeypatch.setattr(
        "solidworks_mcp.security.runtime.check_rate_limit", lambda _client_id: False
    )
    with pytest.raises(SecurityError, match="rate limit exceeded"):
        enforcer.enforce("tool", {"client_id": "c1", "api_key": "expected"})

    monkeypatch.setattr(
        "solidworks_mcp.security.runtime.check_rate_limit", lambda _client_id: True
    )
    with pytest.raises(SecurityError, match="api_key was not provided"):
        enforcer.enforce("tool", {"client_id": "c1"})

    monkeypatch.setattr(
        "solidworks_mcp.security.runtime.validate_api_key",
        lambda provided_key, expected_key: provided_key == expected_key,
    )
    with pytest.raises(SecurityError, match="invalid api_key"):
        enforcer.enforce("tool", {"client_id": "c1", "api_key": "wrong"})

    enforcer.enforce("tool", {"client_id": "c1", "api_key": "expected"})


def test_enforce_auth_not_required_returns_early(monkeypatch) -> None:
    cfg = SimpleNamespace(
        enable_rate_limiting=False,
        api_key_required=False,
        security_level=None,
        api_key=None,
        api_keys=[],
    )
    enforcer = SecurityEnforcer(cfg)
    monkeypatch.setattr(
        "solidworks_mcp.security.runtime.check_rate_limit", lambda _client_id: True
    )
    enforcer.enforce("tool", {"client_id": "x"})


def test_enforce_required_but_no_configured_key(monkeypatch) -> None:
    cfg = SimpleNamespace(
        enable_rate_limiting=False,
        api_key_required=True,
        security_level=None,
        api_key=None,
        api_keys=[],
    )
    enforcer = SecurityEnforcer(cfg)
    monkeypatch.setattr(
        "solidworks_mcp.security.runtime.check_rate_limit", lambda _client_id: True
    )
    with pytest.raises(SecurityError, match="no API key configured"):
        enforcer.enforce("tool", {"client_id": "x", "api_key": "anything"})
