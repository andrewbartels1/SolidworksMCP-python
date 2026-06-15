"""Tests for the local_model router endpoints."""

from __future__ import annotations

from pydantic import BaseModel
from unittest.mock import AsyncMock

import pytest

from solidworks_mcp.ui.routers import local_model as local_model_router
from solidworks_mcp.ui.local_llm import (
    LocalAgentResult,
    LocalLLMConfig,
    LocalModelProbeResult,
    LocalModelPullResult,
    GEMMA_TIERS,
)


# ---------------------------------------------------------------------------
# probe_local_model_endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_endpoint_returns_result(monkeypatch) -> None:
    """probe_local_model_endpoint should call probe_local_model and return result."""
    import solidworks_mcp.ui.local_llm as llm_mod

    spec = GEMMA_TIERS["small"]
    fake_result = LocalModelProbeResult(
        available=True,
        endpoint="http://127.0.0.1:11434",
        openai_endpoint="http://127.0.0.1:11434/v1",
        tier="small",
        ollama_model=spec.ollama,
        service_model=spec.service,
        label=spec.label,
        vram_gb=4.0,
        ram_gb=8.0,
        pulled_models=["gemma4:e2b"],
        tier_already_pulled=True,
        pull_command="",
        status_message="Ollama running.",
        all_tiers={k: v.label for k, v in GEMMA_TIERS.items()},
    )

    monkeypatch.setattr(llm_mod, "probe_local_model", AsyncMock(return_value=fake_result))

    result = await local_model_router.probe_local_model_endpoint()
    assert result.available is True
    assert result.tier == "small"


# ---------------------------------------------------------------------------
# pull_local_model_endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pull_endpoint_success(monkeypatch) -> None:
    """pull_local_model_endpoint should return queued=True on success."""
    import solidworks_mcp.ui.local_llm as llm_mod

    monkeypatch.setattr(
        llm_mod,
        "pull_ollama_model",
        AsyncMock(return_value=LocalModelPullResult(queued=True, model="gemma4:e2b")),
    )

    from solidworks_mcp.ui.local_llm import LocalModelPullRequest

    payload = LocalModelPullRequest(model="gemma4:e2b")
    result = await local_model_router.pull_local_model_endpoint(payload)
    assert result.queued is True
    assert result.model == "gemma4:e2b"


@pytest.mark.asyncio
async def test_pull_endpoint_with_endpoint_override(monkeypatch) -> None:
    """pull_local_model_endpoint should forward endpoint kwarg."""
    import solidworks_mcp.ui.local_llm as llm_mod

    captured: dict = {}

    async def _fake_pull(model, endpoint=None):
        captured["endpoint"] = endpoint
        return LocalModelPullResult(queued=True, model=model)

    monkeypatch.setattr(llm_mod, "pull_ollama_model", _fake_pull)

    from solidworks_mcp.ui.local_llm import LocalModelPullRequest

    payload = LocalModelPullRequest(model="gemma4:e2b", endpoint="http://myhost:11434")
    await local_model_router.pull_local_model_endpoint(payload)
    assert captured["endpoint"] == "http://myhost:11434"


# ---------------------------------------------------------------------------
# query_local_model_endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_endpoint_basic(monkeypatch) -> None:
    """query_local_model_endpoint should invoke run_local_agent and return result."""
    import solidworks_mcp.ui.local_llm as llm_mod

    class _FreeForm(BaseModel):
        text: str = "ok"

    fake_result = LocalAgentResult(success=True, data=_FreeForm(), config=LocalLLMConfig())
    monkeypatch.setattr(llm_mod, "run_local_agent", AsyncMock(return_value=fake_result))

    from solidworks_mcp.ui.local_llm import LocalModelQueryRequest

    payload = LocalModelQueryRequest(prompt="How do I create a sketch?")
    result = await local_model_router.query_local_model_endpoint(payload)
    assert result.success is True


@pytest.mark.asyncio
async def test_query_endpoint_with_endpoint_override(monkeypatch) -> None:
    """query_local_model_endpoint with endpoint override should update config."""
    import solidworks_mcp.ui.local_llm as llm_mod

    class _FreeForm(BaseModel):
        text: str = "ok"

    captured: dict = {}

    async def _fake_run(**kwargs):
        captured["config"] = kwargs.get("config")
        return LocalAgentResult(success=True, data=_FreeForm(), config=LocalLLMConfig())

    monkeypatch.setattr(llm_mod, "run_local_agent", _fake_run)

    from solidworks_mcp.ui.local_llm import LocalModelQueryRequest

    payload = LocalModelQueryRequest(
        prompt="Test",
        endpoint="http://custom:11434",
    )
    await local_model_router.query_local_model_endpoint(payload)
    cfg = captured.get("config")
    assert cfg is not None
    assert cfg.endpoint == "http://custom:11434"
    assert cfg.openai_endpoint == "http://custom:11434/v1"


@pytest.mark.asyncio
async def test_query_endpoint_with_model_override_no_prefix(monkeypatch) -> None:
    """query_local_model_endpoint should prepend 'local:' to model without prefix."""
    import solidworks_mcp.ui.local_llm as llm_mod

    class _FreeForm(BaseModel):
        text: str = "ok"

    captured: dict = {}

    async def _fake_run(**kwargs):
        captured["config"] = kwargs.get("config")
        return LocalAgentResult(success=True, data=_FreeForm(), config=LocalLLMConfig())

    monkeypatch.setattr(llm_mod, "run_local_agent", _fake_run)

    from solidworks_mcp.ui.local_llm import LocalModelQueryRequest

    payload = LocalModelQueryRequest(prompt="Test", model="gemma4:26b")
    await local_model_router.query_local_model_endpoint(payload)
    cfg = captured.get("config")
    assert cfg is not None
    assert cfg.service_model == "local:gemma4:26b"


@pytest.mark.asyncio
async def test_query_endpoint_with_model_override_with_prefix(monkeypatch) -> None:
    """query_local_model_endpoint should not re-prefix 'local:' models."""
    import solidworks_mcp.ui.local_llm as llm_mod

    class _FreeForm(BaseModel):
        text: str = "ok"

    captured: dict = {}

    async def _fake_run(**kwargs):
        captured["config"] = kwargs.get("config")
        return LocalAgentResult(success=True, data=_FreeForm(), config=LocalLLMConfig())

    monkeypatch.setattr(llm_mod, "run_local_agent", _fake_run)

    from solidworks_mcp.ui.local_llm import LocalModelQueryRequest

    payload = LocalModelQueryRequest(prompt="Test", model="local:gemma4:26b")
    await local_model_router.query_local_model_endpoint(payload)
    cfg = captured.get("config")
    assert cfg is not None
    assert cfg.service_model == "local:gemma4:26b"
