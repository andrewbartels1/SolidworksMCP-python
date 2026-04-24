"""Coverage tests for src/solidworks_mcp/ui/local_llm.py."""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.solidworks_mcp.ui.local_llm as local_llm_mod
from src.solidworks_mcp.ui.local_llm import (
    GEMMA_TIERS,
    OLLAMA_DEFAULT_ENDPOINT,
    LocalLLMConfig,
    LocalModelProbeResult,
    _detect_gpu_vram_gb,
    _detect_system_ram_gb,
    _ollama_health,
    _ollama_list_models,
    probe_local_model,
    pull_ollama_model,
    recommend_model_tier,
    run_local_agent,
)


# ---------------------------------------------------------------------------
# LocalLLMConfig.from_env
# ---------------------------------------------------------------------------


def test_local_llm_config_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test local llm config from env defaults."""

    monkeypatch.delenv("SOLIDWORKS_UI_OLLAMA_ENDPOINT", raising=False)
    monkeypatch.delenv("SOLIDWORKS_UI_MODEL", raising=False)
    monkeypatch.delenv("LOCAL_OPENAI_API_KEY", raising=False)
    cfg = LocalLLMConfig.from_env()
    assert cfg.endpoint == OLLAMA_DEFAULT_ENDPOINT
    assert cfg.tier in ("small", "balanced", "large")
    assert cfg.api_key == "local"


def test_local_llm_config_from_env_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test local llm config from env custom."""

    monkeypatch.setenv("SOLIDWORKS_UI_OLLAMA_ENDPOINT", "http://myhost:11434")
    monkeypatch.setenv("SOLIDWORKS_UI_MODEL", "local:gemma4:e4b")
    monkeypatch.setenv("LOCAL_OPENAI_API_KEY", "mykey")
    cfg = LocalLLMConfig.from_env()
    assert cfg.endpoint == "http://myhost:11434"
    assert cfg.tier == "balanced"
    assert cfg.api_key == "mykey"


def test_local_llm_config_from_env_unknown_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test local llm config from env unknown model."""

    monkeypatch.setenv("SOLIDWORKS_UI_MODEL", "local:some-unknown-model")
    cfg = LocalLLMConfig.from_env()
    assert cfg.tier == "small"  # falls back to "small" tier


# ---------------------------------------------------------------------------
# LocalModelProbeResult.to_config
# ---------------------------------------------------------------------------


def test_local_model_probe_result_to_config() -> None:
    """Test local model probe result to config."""

    spec = GEMMA_TIERS["balanced"]
    result = LocalModelProbeResult(
        available=True,
        endpoint=OLLAMA_DEFAULT_ENDPOINT,
        openai_endpoint=f"{OLLAMA_DEFAULT_ENDPOINT}/v1",
        tier="balanced",
        ollama_model=spec.ollama,
        service_model=spec.service,
        label=spec.label,
        vram_gb=8.0,
        ram_gb=16.0,
        pulled_models=["gemma4:e4b"],
        tier_already_pulled=True,
        pull_command="ollama pull gemma4:e4b",
        status_message="Ready",
        all_tiers={k: v.label for k, v in GEMMA_TIERS.items()},
    )
    cfg = result.to_config()
    assert cfg.tier == "balanced"
    assert cfg.ollama_model == spec.ollama
    assert cfg.endpoint == OLLAMA_DEFAULT_ENDPOINT


# ---------------------------------------------------------------------------
# recommend_model_tier
# ---------------------------------------------------------------------------


def test_recommend_model_tier_small() -> None:
    """Test recommend model tier small."""

    assert recommend_model_tier(vram_gb=0, ram_gb=8) == "small"


def test_recommend_model_tier_balanced() -> None:
    """Test recommend model tier balanced."""

    assert recommend_model_tier(vram_gb=8, ram_gb=16) == "balanced"


def test_recommend_model_tier_large() -> None:
    """Test recommend model tier large."""

    assert recommend_model_tier(vram_gb=24, ram_gb=64) == "large"


def test_recommend_model_tier_fallback_small() -> None:
    """When no tier fits (0 RAM), still returns 'small' as a safe default."""
    assert recommend_model_tier(vram_gb=0, ram_gb=0) == "small"


# ---------------------------------------------------------------------------
# _detect_gpu_vram_gb
# ---------------------------------------------------------------------------


def test_detect_gpu_vram_gb_nvidia_smi_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test detect gpu vram gb nvidia smi success."""

    monkeypatch.setattr(
        local_llm_mod.subprocess,
        "check_output",
        lambda *a, **k: "8192\n",
    )
    result = _detect_gpu_vram_gb()
    assert result == pytest.approx(8.0, abs=0.1)


def test_detect_gpu_vram_gb_fallback_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Returns 0.0 when all detection methods fail."""

    def _always_raise(*a, **k) -> None:
        """Test always raise."""

        raise OSError("not found")

    monkeypatch.setattr(local_llm_mod.subprocess, "check_output", _always_raise)
    result = _detect_gpu_vram_gb()
    assert result == 0.0


# ---------------------------------------------------------------------------
# _detect_system_ram_gb
# ---------------------------------------------------------------------------


def test_detect_system_ram_gb_returns_float() -> None:
    """Test detect system ram gb returns float."""

    result = _detect_system_ram_gb()
    assert isinstance(result, float)
    # On any modern machine (or CI) there should be some RAM
    assert result >= 0.0


def test_detect_system_ram_gb_no_psutil(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falls back gracefully when psutil is not available."""
    original_psutil = sys.modules.get("psutil", "ABSENT")
    sys.modules["psutil"] = None  # type: ignore[assignment]
    try:
        result = _detect_system_ram_gb()
        assert isinstance(result, float)
    finally:
        if original_psutil == "ABSENT":
            del sys.modules["psutil"]
        else:
            sys.modules["psutil"] = original_psutil  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# _ollama_health
# ---------------------------------------------------------------------------


async def test_ollama_health_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test ollama health available."""

    class _FakeResp:
        """Test fake resp."""

        status = 200

        def __enter__(self) -> "_FakeResp":
            """Test enter."""

            return self

        def __exit__(self, *a: object) -> None:
            """Test exit."""

            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp())
    assert await _ollama_health() is True


async def test_ollama_health_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test ollama health unavailable."""

    def _raise(*a: object, **k: object) -> None:
        """Test raise."""

        raise ConnectionRefusedError("no server")

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    assert await _ollama_health() is False


# ---------------------------------------------------------------------------
# _ollama_list_models
# ---------------------------------------------------------------------------


async def test_ollama_list_models_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test ollama list models success."""

    data = json.dumps({"models": [{"name": "gemma4:e2b"}, {"name": "llama3"}]}).encode()

    class _FakeResp:
        """Test fake resp."""

        def read(self) -> bytes:
            """Test read."""

            return data

        def __enter__(self) -> "_FakeResp":
            """Test enter."""

            return self

        def __exit__(self, *a: object) -> None:
            """Test exit."""

            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp())
    result = await _ollama_list_models()
    assert "gemma4:e2b" in result
    assert "llama3" in result


async def test_ollama_list_models_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test ollama list models failure."""

    def _raise(*a: object, **k: object) -> None:
        """Test raise."""

        raise ConnectionRefusedError()

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    result = await _ollama_list_models()
    assert result == []


# ---------------------------------------------------------------------------
# probe_local_model
# ---------------------------------------------------------------------------


async def test_probe_local_model_available_with_model_pulled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test probe local model available with model pulled."""

    monkeypatch.setattr(local_llm_mod, "_detect_gpu_vram_gb", lambda: 8.0)
    monkeypatch.setattr(local_llm_mod, "_detect_system_ram_gb", lambda: 16.0)

    async def _health(*a: object, **k: object) -> bool:
        """Test health."""

        return True

    async def _list_models(*a: object, **k: object) -> list[str]:
        """Test list models."""

        return ["gemma4:e4b", "llama3:8b"]

    monkeypatch.setattr(local_llm_mod, "_ollama_health", _health)
    monkeypatch.setattr(local_llm_mod, "_ollama_list_models", _list_models)

    result = await probe_local_model()
    assert result.available is True
    assert result.tier_already_pulled is True
    assert "Ready" in result.status_message


async def test_probe_local_model_available_model_not_pulled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test probe local model available model not pulled."""

    monkeypatch.setattr(local_llm_mod, "_detect_gpu_vram_gb", lambda: 8.0)
    monkeypatch.setattr(local_llm_mod, "_detect_system_ram_gb", lambda: 16.0)

    async def _health(*a: object, **k: object) -> bool:
        """Test health."""

        return True

    async def _list_models(*a: object, **k: object) -> list[str]:
        """Test list models."""

        return []  # no models pulled yet

    monkeypatch.setattr(local_llm_mod, "_ollama_health", _health)
    monkeypatch.setattr(local_llm_mod, "_ollama_list_models", _list_models)

    result = await probe_local_model()
    assert result.available is True
    assert result.tier_already_pulled is False
    assert "ollama pull" in result.status_message


async def test_probe_local_model_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test probe local model unavailable."""

    monkeypatch.setattr(local_llm_mod, "_detect_gpu_vram_gb", lambda: 0.0)
    monkeypatch.setattr(local_llm_mod, "_detect_system_ram_gb", lambda: 8.0)

    async def _health(*a: object, **k: object) -> bool:
        """Test health."""

        return False

    async def _list_models(*a: object, **k: object) -> list[str]:
        """Test list models."""

        return []

    monkeypatch.setattr(local_llm_mod, "_ollama_health", _health)
    monkeypatch.setattr(local_llm_mod, "_ollama_list_models", _list_models)

    result = await probe_local_model()
    assert result.available is False
    assert "not running" in result.status_message


async def test_probe_local_model_custom_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test probe local model custom endpoint."""

    monkeypatch.setattr(local_llm_mod, "_detect_gpu_vram_gb", lambda: 0.0)
    monkeypatch.setattr(local_llm_mod, "_detect_system_ram_gb", lambda: 8.0)

    async def _health(*a: object, **k: object) -> bool:
        """Test health."""

        return False

    async def _list_models(*a: object, **k: object) -> list[str]:
        """Test list models."""

        return []

    monkeypatch.setattr(local_llm_mod, "_ollama_health", _health)
    monkeypatch.setattr(local_llm_mod, "_ollama_list_models", _list_models)

    result = await probe_local_model(endpoint="http://myhost:11434")
    assert result.endpoint == "http://myhost:11434"


# ---------------------------------------------------------------------------
# pull_ollama_model
# ---------------------------------------------------------------------------


async def test_pull_ollama_model_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test pull ollama model success."""

    pull_resp = json.dumps({"status": "success"}).encode()

    class _FakeResp:
        """Test fake resp."""

        def read(self) -> bytes:
            """Test read."""

            return pull_resp

        def __enter__(self) -> "_FakeResp":
            """Test enter."""

            return self

        def __exit__(self, *a: object) -> None:
            """Test exit."""

            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp())
    result = await pull_ollama_model(model="gemma4:e2b")
    assert result.queued is True
    assert result.model == "gemma4:e2b"
    assert result.error is None


async def test_pull_ollama_model_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test pull ollama model connection failure."""

    def _raise(*a: object, **k: object) -> None:
        """Test raise."""

        raise ConnectionRefusedError("Ollama not running")

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    result = await pull_ollama_model(model="gemma4:e2b")
    assert result.queued is False
    assert result.error is not None


async def test_pull_ollama_model_custom_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test pull ollama model custom endpoint."""

    pull_resp = json.dumps({"status": "success"}).encode()

    class _FakeResp:
        """Test fake resp."""

        def read(self) -> bytes:
            """Test read."""

            return pull_resp

        def __enter__(self) -> "_FakeResp":
            """Test enter."""

            return self

        def __exit__(self, *a: object) -> None:
            """Test exit."""

            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp())
    result = await pull_ollama_model(model="gemma4:e4b", endpoint="http://myhost:11434")
    assert result.queued is True


# ---------------------------------------------------------------------------
# run_local_agent — patching pydantic_ai.Agent directly
# ---------------------------------------------------------------------------


async def test_run_local_agent_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run local agent success."""

    from pydantic import BaseModel

    import pydantic_ai
    import pydantic_ai.models.openai
    import pydantic_ai.providers.openai

    class _Out(BaseModel):
        """Test out."""

        answer: str = "ok"

    fake_data = _Out(answer="SolidWorks is great")
    mock_result = MagicMock()
    mock_result.data = fake_data

    mock_agent_instance = AsyncMock()
    mock_agent_instance.run.return_value = mock_result

    monkeypatch.setattr(
        pydantic_ai, "Agent", MagicMock(return_value=mock_agent_instance)
    )
    monkeypatch.setattr(
        pydantic_ai.models.openai,
        "OpenAIChatModel",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        pydantic_ai.providers.openai,
        "OpenAIProvider",
        MagicMock(return_value=MagicMock()),
    )

    result = await run_local_agent(
        system_prompt="You are a CAD assistant.",
        user_prompt="What is a sketch?",
        result_type=_Out,
    )
    assert result.success is True
    assert isinstance(result.data, _Out)


async def test_run_local_agent_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run local agent exception."""

    from pydantic import BaseModel

    import pydantic_ai
    import pydantic_ai.models.openai
    import pydantic_ai.providers.openai

    class _Out(BaseModel):
        """Test out."""

        text: str = ""

    mock_agent_instance = AsyncMock()
    mock_agent_instance.run.side_effect = RuntimeError("model crashed")

    monkeypatch.setattr(
        pydantic_ai, "Agent", MagicMock(return_value=mock_agent_instance)
    )
    monkeypatch.setattr(
        pydantic_ai.models.openai,
        "OpenAIChatModel",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        pydantic_ai.providers.openai,
        "OpenAIProvider",
        MagicMock(return_value=MagicMock()),
    )

    result = await run_local_agent(
        system_prompt="test",
        user_prompt="test",
        result_type=_Out,
    )
    assert result.success is False
    assert "model crashed" in result.error


async def test_run_local_agent_recoverable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test run local agent recoverable failure."""

    from pydantic import BaseModel

    import pydantic_ai
    import pydantic_ai.models.openai
    import pydantic_ai.providers.openai
    from src.solidworks_mcp.agents.schemas import RecoverableFailure

    class _Out(BaseModel):
        """Test out."""

        text: str = ""

    fake_failure = RecoverableFailure(explanation="Could not parse response")
    mock_result = MagicMock()
    mock_result.data = fake_failure

    mock_agent_instance = AsyncMock()
    mock_agent_instance.run.return_value = mock_result

    monkeypatch.setattr(
        pydantic_ai, "Agent", MagicMock(return_value=mock_agent_instance)
    )
    monkeypatch.setattr(
        pydantic_ai.models.openai,
        "OpenAIChatModel",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        pydantic_ai.providers.openai,
        "OpenAIProvider",
        MagicMock(return_value=MagicMock()),
    )

    result = await run_local_agent(
        system_prompt="test",
        user_prompt="test",
        result_type=_Out,
    )
    assert result.success is False
    assert "parse" in result.error.lower()


async def test_run_local_agent_with_rag_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """RAG augmentation path: injects context into system_prompt."""
    from pydantic import BaseModel

    import pydantic_ai
    import pydantic_ai.models.openai
    import pydantic_ai.providers.openai

    class _Out(BaseModel):
        """Test out."""

        text: str = "done"

    mock_result = MagicMock()
    mock_result.data = _Out()

    mock_agent_instance = AsyncMock()
    mock_agent_instance.run.return_value = mock_result

    monkeypatch.setattr(
        pydantic_ai, "Agent", MagicMock(return_value=mock_agent_instance)
    )
    monkeypatch.setattr(
        pydantic_ai.models.openai,
        "OpenAIChatModel",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        pydantic_ai.providers.openai,
        "OpenAIProvider",
        MagicMock(return_value=MagicMock()),
    )

    # Patch query_solidworks_api_docs to return a fake context string
    import src.solidworks_mcp.agents.vector_rag as vr_mod

    monkeypatch.setattr(
        vr_mod, "query_solidworks_api_docs", lambda *a, **k: "## API context"
    )

    result = await run_local_agent(
        system_prompt="Base system prompt.",
        user_prompt="Sketch question?",
        result_type=_Out,
        rag_query="sketch",
        rag_namespace="solidworks-api-docs",
    )
    assert result.success is True


async def test_run_local_agent_rag_import_error_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAG failure is non-fatal; agent still runs normally."""
    from pydantic import BaseModel

    import pydantic_ai
    import pydantic_ai.models.openai
    import pydantic_ai.providers.openai

    class _Out(BaseModel):
        """Test out."""

        text: str = "done"

    mock_result = MagicMock()
    mock_result.data = _Out()

    mock_agent_instance = AsyncMock()
    mock_agent_instance.run.return_value = mock_result

    monkeypatch.setattr(
        pydantic_ai, "Agent", MagicMock(return_value=mock_agent_instance)
    )
    monkeypatch.setattr(
        pydantic_ai.models.openai,
        "OpenAIChatModel",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        pydantic_ai.providers.openai,
        "OpenAIProvider",
        MagicMock(return_value=MagicMock()),
    )

    import src.solidworks_mcp.agents.vector_rag as vr_mod

    monkeypatch.setattr(
        vr_mod,
        "query_solidworks_api_docs",
        lambda *a, **k: (_ for _ in ()).throw(ImportError("no faiss")),
    )

    result = await run_local_agent(
        system_prompt="test",
        user_prompt="test",
        result_type=_Out,
        rag_query="sketch",
    )
    # Should still succeed despite RAG failure
    assert result.success is True


async def test_run_local_agent_rag_other_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uses query_design_knowledge when namespace != 'solidworks-api-docs'."""
    from pydantic import BaseModel

    import pydantic_ai
    import pydantic_ai.models.openai
    import pydantic_ai.providers.openai

    class _Out(BaseModel):
        """Test out."""

        text: str = "done"

    mock_result = MagicMock()
    mock_result.data = _Out()

    mock_agent_instance = AsyncMock()
    mock_agent_instance.run.return_value = mock_result

    monkeypatch.setattr(
        pydantic_ai, "Agent", MagicMock(return_value=mock_agent_instance)
    )
    monkeypatch.setattr(
        pydantic_ai.models.openai,
        "OpenAIChatModel",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        pydantic_ai.providers.openai,
        "OpenAIProvider",
        MagicMock(return_value=MagicMock()),
    )

    import src.solidworks_mcp.agents.vector_rag as vr_mod

    monkeypatch.setattr(
        vr_mod, "query_design_knowledge", lambda *a, **k: "## design context"
    )

    result = await run_local_agent(
        system_prompt="test",
        user_prompt="test",
        result_type=_Out,
        rag_query="sketch",
        rag_namespace="engineering-reference",
    )
    assert result.success is True
