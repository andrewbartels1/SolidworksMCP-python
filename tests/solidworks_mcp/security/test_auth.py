"""Tests for ``solidworks_mcp.security.auth``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from solidworks_mcp.security import auth as auth_mod
from solidworks_mcp.security import cors as cors_mod
from solidworks_mcp.security import setup_security
from solidworks_mcp.security.auth import require_auth, setup_authentication


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
        "solidworks_mcp.config",
        SimpleNamespace(SecurityLevel=_Level),
    )

    await setup_security(object(), minimal_cfg)

    calls = {"auth": 0, "cors": 0, "rate": 0}
    monkeypatch.setattr(
        "solidworks_mcp.security.setup_authentication",
        lambda *_: calls.__setitem__("auth", calls["auth"] + 1),
    )
    monkeypatch.setattr(
        "solidworks_mcp.security.setup_cors",
        lambda *_: calls.__setitem__("cors", calls["cors"] + 1),
    )
    monkeypatch.setattr(
        "solidworks_mcp.security.setup_rate_limiting",
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


class _PayloadWithModelDump:
    """Test payload with model dump."""

    def __init__(self, api_key: str):
        """Test init."""

        self._api_key = api_key

    def model_dump(self) -> dict[str, str]:
        """Test model dump."""

        return {"api_key": self._api_key}


class _FakeSecret:
    """Test fake secret."""

    def __init__(self, value: str):
        """Test init."""

        self._value = value

    def get_secret_value(self) -> str:
        """Test get secret value."""

        return self._value


@pytest.mark.asyncio
async def test_setup_authentication_sets_none_mode_and_handles_plain_object() -> None:
    """Test setup authentication sets none mode and handles plain object."""

    mcp = SimpleNamespace()
    cfg_none = SimpleNamespace(api_key=None, api_keys=[], api_key_required=False)
    setup_authentication(mcp, cfg_none)
    assert mcp._security_auth_enabled is True
    assert mcp._security_auth_mode == "none"

    # object() cannot receive attributes; function should safely no-op.
    setup_authentication(object(), cfg_none)


@pytest.mark.asyncio
async def test_require_auth_minimal_security_bypasses_key_checks() -> None:
    """Test require auth minimal security bypasses key checks."""

    cfg = SimpleNamespace(security_level="minimal", api_key_required=True, api_key="x")

    @require_auth(cfg)
    async def _endpoint(input_data):
        """Test endpoint."""

        return {"ok": input_data}

    result = await _endpoint(input_data={})
    assert result["ok"] == {}


@pytest.mark.asyncio
async def test_require_auth_no_key_config_bypasses() -> None:
    """Test require auth no key config bypasses."""

    cfg = SimpleNamespace(
        security_level="strict",
        api_key_required=False,
        api_key=None,
        api_keys=[],
    )

    @require_auth(cfg)
    async def _endpoint(input_data):
        """Test endpoint."""

        return "allowed"

    assert await _endpoint(input_data={}) == "allowed"


@pytest.mark.asyncio
async def test_require_auth_accepts_model_dump_payload_and_secret_api_key() -> None:
    """Test require auth accepts model dump payload and secret api key."""

    cfg = SimpleNamespace(
        security_level="strict",
        api_key_required=True,
        api_key=_FakeSecret("secret-1"),
        api_keys=[],
    )

    @require_auth(cfg)
    async def _endpoint(input_data):
        """Test endpoint."""

        return "ok"

    assert await _endpoint(input_data=_PayloadWithModelDump("secret-1")) == "ok"


@pytest.mark.asyncio
async def test_require_auth_uses_first_api_keys_entry_when_primary_missing() -> None:
    """Test require auth uses first api keys entry when primary missing."""

    cfg = SimpleNamespace(
        security_level="strict",
        api_key_required=True,
        api_key=None,
        api_keys=["k-first", "k-second"],
    )

    @require_auth(cfg)
    async def _endpoint(input_data):
        """Test endpoint."""

        return "ok"

    assert await _endpoint(input_data={"api_key": "k-first"}) == "ok"


@pytest.mark.asyncio
async def test_require_auth_rejects_invalid_key_from_positional_payload() -> None:
    """Test require auth rejects invalid key from positional payload."""

    cfg = SimpleNamespace(
        security_level="strict",
        api_key_required=True,
        api_key="expected",
        api_keys=[],
    )

    @require_auth(cfg)
    async def _endpoint(input_data):
        """Test endpoint."""

        return "never"

    with pytest.raises(RuntimeError, match="authentication failed"):
        await _endpoint({"api_key": "wrong"})
