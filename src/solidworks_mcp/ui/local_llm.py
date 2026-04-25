"""Local LLM integration helpers for the SolidWorks MCP UI.

Provides three layers of typed abstraction:

1. **Hardware** – detect GPU VRAM / system RAM and pick the right Gemma tier. 2.
**Config** – ``LocalLLMConfig`` is the single source of truth for endpoint, model name,
and tier choice, shared by the UI, server endpoints, and the pydantic-ai agent runner.
3. **Agent runner** – ``run_local_agent()`` mirrors ``_run_structured_agent`` in
``service.py`` but routes exclusively to a local Ollama server.  Both accept any
``BaseModel`` subclass as ``result_type`` so callers get a fully typed, validated
response regardless of which backend they use.

Model tiers (Gemma 4 family via Ollama's OpenAI-compatible API): small   : gemma4:e2b
(~0-4 GB VRAM / CPU-capable) — edge and smoke tests balanced: gemma4:e4b (~8 GB VRAM) —
recommended default for local planning large   : gemma4:26b (~18 GB VRAM) — workstation-
class local evaluation

Usage::

from solidworks_mcp.ui.local_llm import probe_local_model, run_local_agent from
solidworks_mcp.agents.schemas import ClarificationResponse

probe = await probe_local_model()          # LocalModelProbeResult result = await
run_local_agent( system_prompt="You are a SolidWorks CAD assistant.", user_prompt="How
many sketch constraints are needed for a slot?", result_type=ClarificationResponse,
config=probe.to_config(), )
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import subprocess
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# TypeVar for structured agent outputs
_T = TypeVar("_T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OLLAMA_DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
OLLAMA_OPENAI_ENDPOINT = f"{OLLAMA_DEFAULT_ENDPOINT}/v1"

# ---------------------------------------------------------------------------
# Tier spec — typed model for each hardware tier
# ---------------------------------------------------------------------------


class GemmaTierSpec(BaseModel):
    """Hardware and model metadata for a single Gemma inference tier.

    Attributes:
        label (str): The label value.
        min_ram_gb (float): The min ram gb value.
        min_vram_gb (float): The min vram gb value.
        ollama (str): The ollama value.
        service (str): The service value.
    """

    ollama: str = Field(description="Ollama model tag, e.g. 'gemma4:e4b'")
    service: str = Field(description="service.py model string, e.g. 'local:gemma4:e4b'")
    label: str = Field(description="Human-readable description shown in UI toasts")
    min_vram_gb: float = Field(ge=0, description="Minimum GPU VRAM in GB (0 = CPU ok)")
    min_ram_gb: float = Field(ge=0, description="Minimum system RAM in GB")


# Gemma 3 / Gemma 4 model tiers — typed registry
GEMMA_TIERS: dict[str, GemmaTierSpec] = {
    "small": GemmaTierSpec(
        ollama="gemma4:e2b",
        service="local:gemma4:e2b",
        label="Gemma 4 E2B (small — CPU or 4 GB VRAM)",
        min_vram_gb=0,
        min_ram_gb=8,
    ),
    "balanced": GemmaTierSpec(
        ollama="gemma4:e4b",
        service="local:gemma4:e4b",
        label="Gemma 4 E4B (balanced — 8 GB VRAM)",
        min_vram_gb=8,
        min_ram_gb=16,
    ),
    "large": GemmaTierSpec(
        ollama="gemma4:26b",
        service="local:gemma4:26b",
        label="Gemma 4 26B (large — 18 GB VRAM)",
        min_vram_gb=18,
        min_ram_gb=32,
    ),
}

# ---------------------------------------------------------------------------
# Shared config — single source of truth for LLM connection settings
# ---------------------------------------------------------------------------


class LocalLLMConfig(BaseModel):
    """Runtime configuration for a local Ollama LLM connection.

    Passed from the probe result into ``run_local_agent()`` or directly into
    ``_build_agent_model()`` in service.py to keep settings consistent across all layers (UI
    state, server endpoints, pydantic-ai agent runner).

    Attributes:
        api_key (str): The api key value.
        endpoint (str): The endpoint value.
        ollama_model (str): The ollama model value.
        openai_endpoint (str): The openai endpoint value.
        service_model (str): The service model value.
        tier (Literal["small", "balanced", "large"]): The tier value.
    """

    endpoint: str = Field(
        default=OLLAMA_DEFAULT_ENDPOINT,
        description="Ollama base URL (without /v1 suffix)",
    )
    openai_endpoint: str = Field(
        default=OLLAMA_OPENAI_ENDPOINT,
        description="OpenAI-compatible endpoint for pydantic-ai",
    )
    tier: Literal["small", "balanced", "large"] = Field(default="balanced")
    ollama_model: str = Field(default="gemma4:e4b")
    service_model: str = Field(default="local:gemma4:e4b")
    api_key: str = Field(
        default="local",
        description="API key sent to Ollama (ignored by Ollama but required by OpenAI client)",
    )

    @classmethod
    def from_env(cls) -> LocalLLMConfig:
        """Build config from environment variables, falling back to defaults.

        Returns:
            LocalLLMConfig: The result produced by the operation.
        """
        endpoint = os.getenv("SOLIDWORKS_UI_OLLAMA_ENDPOINT", OLLAMA_DEFAULT_ENDPOINT)
        service_model = os.getenv("SOLIDWORKS_UI_MODEL", "local:gemma4:e4b")
        tier = "small"
        for t, spec in GEMMA_TIERS.items():
            if spec.service == service_model:
                tier = t
                break
        spec = GEMMA_TIERS[tier]
        return cls(
            endpoint=endpoint,
            openai_endpoint=f"{endpoint}/v1",
            tier=tier,  # type: ignore[arg-type]
            ollama_model=spec.ollama,
            service_model=spec.service,
            api_key=os.getenv("LOCAL_OPENAI_API_KEY", "local"),
        )


# ---------------------------------------------------------------------------
# Probe result — typed response returned by the /api/ui/local-model/probe endpoint
# ---------------------------------------------------------------------------
class LocalModelProbeResult(BaseModel):
    """Full hardware-detection and Ollama availability result.

    Returned by ``probe_local_model()`` and serialised as the JSON response from ``GET
    /api/ui/local-model/probe``.  The ``to_config()`` helper converts directly into a
    ``LocalLLMConfig`` ready for ``run_local_agent()``.

    Attributes:
        all_tiers (dict[str, str]): The all tiers value.
        available (bool): The available value.
        endpoint (str): The endpoint value.
        label (str): The label value.
        ollama_model (str): The ollama model value.
        openai_endpoint (str): The openai endpoint value.
        pull_command (str): The pull command value.
        pulled_models (list[str]): The pulled models value.
        ram_gb (float): The ram gb value.
        service_model (str): The service model value.
        status_message (str): The status message value.
        tier (Literal["small", "balanced", "large"]): The tier value.
        tier_already_pulled (bool): The tier already pulled value.
        vram_gb (float): The vram gb value.
    """

    available: bool = Field(description="True if Ollama responded to /api/tags")
    endpoint: str
    openai_endpoint: str = Field(description="OpenAI-compatible URL (/v1 suffix)")
    tier: Literal["small", "balanced", "large"]
    ollama_model: str
    service_model: str = Field(
        description="Model string for service.py, e.g. 'local:gemma4:e4b'"
    )
    label: str
    vram_gb: float = Field(ge=0)
    ram_gb: float = Field(ge=0)
    pulled_models: list[str] = Field(default_factory=list)
    tier_already_pulled: bool
    pull_command: str
    status_message: str
    all_tiers: dict[str, str] = Field(
        description="Map of tier name → human label for all supported tiers"
    )

    def to_config(self) -> LocalLLMConfig:
        """Convert probe result into a ready-to-use ``LocalLLMConfig``.

        Returns:
            LocalLLMConfig: The result produced by the operation.
        """
        return LocalLLMConfig(
            endpoint=self.endpoint,
            openai_endpoint=self.openai_endpoint,
            tier=self.tier,
            ollama_model=self.ollama_model,
            service_model=self.service_model,
        )


class LocalModelPullResult(BaseModel):
    """Result from ``POST /api/ui/local-model/pull``.

    Attributes:
        error (str | None): The error value.
        model (str): The model value.
        queued (bool): The queued value.
        response (dict[str, Any] | None): The response value.
    """

    queued: bool
    model: str
    error: str | None = Field(default=None)
    response: dict[str, Any] | None = Field(default=None)


class LocalModelPullRequest(BaseModel):
    """Request body for ``POST /api/ui/local-model/pull``.

    Attributes:
        endpoint (str | None): The endpoint value.
        model (str): The model value.
    """

    model: str = Field(description="Ollama model tag to pull, e.g. 'gemma4:e4b'")
    endpoint: str | None = Field(
        default=None,
        description="Override Ollama base URL (omit to use env / default)",
    )


class LocalModelQueryRequest(BaseModel):
    """Request body for ``POST /api/ui/local-model/query``.

    Attributes:
        endpoint (str | None): The endpoint value.
        model (str | None): The model value.
        prompt (str): The prompt value.
        system_prompt (str): The system prompt value.
    """

    prompt: str = Field(min_length=1, description="User question or task description")
    system_prompt: str = Field(
        default="You are a SolidWorks CAD design assistant.",
        description="Instruction preamble sent to the LLM",
    )
    model: str | None = Field(
        default=None,
        description="Override model (bare name or 'local:...' prefix). Omit to use env / detected tier.",
    )
    endpoint: str | None = Field(
        default=None,
        description="Override Ollama base URL. Omit to use env / default.",
    )


# ---------------------------------------------------------------------------
# Agent result envelope — uniform wrapper for structured LLM outputs
# ---------------------------------------------------------------------------


class LocalAgentResult(BaseModel, Generic[_T]):
    """Typed envelope wrapping a structured pydantic-ai agent response.

    ``data`` holds the validated ``result_type`` instance; ``config`` echoes back the
    ``LocalLLMConfig`` used so callers can log or audit provenance. Set ``success=False``
    and ``error`` when the agent returned a ``RecoverableFailure`` or raised an exception.

    Attributes:
        config (LocalLLMConfig): The config value.
        data (Any): The data value.
        error (str | None): The error value.
        retry_hint (str | None): The retry hint value.
        success (bool): The success value.
    """

    success: bool
    data: Any = Field(default=None, description="Validated result_type instance")
    error: str | None = Field(default=None)
    retry_hint: str | None = Field(default=None)
    config: LocalLLMConfig


# ---------------------------------------------------------------------------
# VRAM / RAM detection
# ---------------------------------------------------------------------------


def _detect_gpu_vram_gb() -> float:
    """Return best-effort GPU VRAM estimate in GB, or 0.0 on failure.

    Returns:
        float: The computed numeric result.
    """
    # Try nvidia-smi first
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL,
            timeout=5,
            text=True,
        )
        mib = max(
            int(x.strip()) for x in out.strip().splitlines() if x.strip().isdigit()
        )
        return mib / 1024.0
    except Exception:
        pass

    # Try wmic on Windows
    if platform.system() == "Windows":
        try:
            out = subprocess.check_output(
                ["wmic", "path", "win32_VideoController", "get", "AdapterRAM"],
                stderr=subprocess.DEVNULL,
                timeout=5,
                text=True,
            )
            bytes_vals = [
                int(x.strip())
                for x in out.splitlines()
                if x.strip().lstrip("-").isdigit() and int(x.strip()) > 0
            ]
            if bytes_vals:
                return max(bytes_vals) / (1024**3)
        except Exception:
            pass

    return 0.0


def _detect_system_ram_gb() -> float:
    """Return total system RAM in GB.

    Returns:
        float: The computed numeric result.
    """
    try:
        import psutil  # optional dependency

        return psutil.virtual_memory().total / (1024**3)
    except ImportError:
        pass

    if platform.system() == "Windows":
        try:
            out = subprocess.check_output(
                ["wmic", "computersystem", "get", "TotalPhysicalMemory"],
                stderr=subprocess.DEVNULL,
                timeout=5,
                text=True,
            )
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    return int(line) / (1024**3)
        except Exception:
            pass

    return 0.0


def recommend_model_tier(vram_gb: float = 0.0, ram_gb: float = 0.0) -> str:
    """Return 'small' | 'balanced' | 'large' based on available hardware.

    Args:
        vram_gb (float): The vram gb value. Defaults to 0.0.
        ram_gb (float): The ram gb value. Defaults to 0.0.

    Returns:
        str: The resulting text value.
    """
    for tier in ("large", "balanced", "small"):
        spec = GEMMA_TIERS[tier]
        if vram_gb >= spec.min_vram_gb and ram_gb >= spec.min_ram_gb:
            return tier
    return "small"  # always runnable with quantized 4B


# ---------------------------------------------------------------------------
# Ollama probe
# ---------------------------------------------------------------------------


async def _ollama_health(endpoint: str = OLLAMA_DEFAULT_ENDPOINT) -> bool:
    """Return True if Ollama HTTP server is responding.

    Args:
        endpoint (str): The endpoint value. Defaults to OLLAMA_DEFAULT_ENDPOINT.

    Returns:
        bool: True if ollama health, otherwise False.
    """
    import urllib.request

    loop = asyncio.get_event_loop()
    try:

        def _get() -> bool:
            """Build internal get.

            Returns:
                bool: True if get, otherwise False.
            """

            try:
                with urllib.request.urlopen(f"{endpoint}/api/tags", timeout=3) as r:
                    return r.status == 200
            except Exception:
                return False

        return await loop.run_in_executor(None, _get)
    except Exception:
        return False


async def _ollama_list_models(endpoint: str = OLLAMA_DEFAULT_ENDPOINT) -> list[str]:
    """Return list of model names currently pulled in Ollama.

    Args:
        endpoint (str): The endpoint value. Defaults to OLLAMA_DEFAULT_ENDPOINT.

    Returns:
        list[str]: A list containing the resulting items.
    """
    import json
    import urllib.request

    loop = asyncio.get_event_loop()

    def _get() -> list[str]:
        """Build internal get.

        Returns:
            list[str]: A list containing the resulting items.
        """

        try:
            with urllib.request.urlopen(f"{endpoint}/api/tags", timeout=5) as r:
                data = json.loads(r.read())
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []

    return await loop.run_in_executor(None, _get)


async def probe_local_model(
    endpoint: str | None = None,
) -> LocalModelProbeResult:
    """Probe Ollama for availability and return a typed recommendation result.

    The returned ``LocalModelProbeResult`` can be forwarded directly as a FastAPI JSON
    response (it is a ``BaseModel``).  Call ``.to_config()`` on the result to build a
    ``LocalLLMConfig`` for ``run_local_agent()``.

    Args:
        endpoint (str | None): The endpoint value. Defaults to None.

    Returns:
        LocalModelProbeResult: The result produced by the operation.
    """
    resolved_endpoint = endpoint or os.getenv(
        "SOLIDWORKS_UI_OLLAMA_ENDPOINT", OLLAMA_DEFAULT_ENDPOINT
    )

    vram_gb = _detect_gpu_vram_gb()
    ram_gb = _detect_system_ram_gb()
    tier = recommend_model_tier(vram_gb=vram_gb, ram_gb=ram_gb)
    spec = GEMMA_TIERS[tier]

    available = await _ollama_health(resolved_endpoint)
    pulled_models: list[str] = []
    if available:
        pulled_models = await _ollama_list_models(resolved_endpoint)

    tier_model = spec.ollama
    tier_already_pulled = any(tier_model in m for m in pulled_models)

    if not available:
        status = (
            f"Ollama is not running at {resolved_endpoint}. "
            "Install from https://ollama.com and run: ollama serve"
        )
    elif tier_already_pulled:
        status = f"Ready: {spec.label} is loaded in Ollama."
    else:
        status = (
            f"Ollama is running. Pull the recommended model with: "
            f"ollama pull {tier_model}"
        )

    return LocalModelProbeResult(
        available=available,
        endpoint=resolved_endpoint,
        openai_endpoint=f"{resolved_endpoint}/v1",
        tier=tier,  # type: ignore[arg-type]
        ollama_model=tier_model,
        service_model=spec.service,
        label=spec.label,
        vram_gb=round(vram_gb, 1),
        ram_gb=round(ram_gb, 1),
        pulled_models=pulled_models,
        tier_already_pulled=tier_already_pulled,
        pull_command=f"ollama pull {tier_model}",
        status_message=status,
        all_tiers={k: v.label for k, v in GEMMA_TIERS.items()},
    )


async def pull_ollama_model(
    model: str,
    endpoint: str | None = None,
) -> LocalModelPullResult:
    """Trigger an Ollama model pull. Runs in a thread; returns immediately.

    Returns a typed ``LocalModelPullResult`` with ``queued=True`` on success.

    Args:
        model (str): The model value.
        endpoint (str | None): The endpoint value. Defaults to None.

    Returns:
        LocalModelPullResult: The result produced by the operation.
    """
    import json
    import urllib.request

    resolved_endpoint = endpoint or os.getenv(
        "SOLIDWORKS_UI_OLLAMA_ENDPOINT", OLLAMA_DEFAULT_ENDPOINT
    )
    loop = asyncio.get_event_loop()

    def _pull() -> LocalModelPullResult:
        """Build internal pull.

        Returns:
            LocalModelPullResult: The result produced by the operation.
        """

        payload = json.dumps({"name": model, "stream": False}).encode()
        req = urllib.request.Request(
            f"{resolved_endpoint}/api/pull",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                body = json.loads(r.read())
                return LocalModelPullResult(queued=True, model=model, response=body)
        except Exception as exc:
            return LocalModelPullResult(queued=False, model=model, error=str(exc))

    return await loop.run_in_executor(None, _pull)


# ---------------------------------------------------------------------------
# pydantic-ai agent runner — structured local LLM inference
# ---------------------------------------------------------------------------
async def run_local_agent(
    *,
    system_prompt: str,
    user_prompt: str,
    result_type: type[_T],
    config: LocalLLMConfig | None = None,
    rag_query: str | None = None,
    rag_namespace: str = "solidworks-api-docs",
) -> LocalAgentResult[_T]:
    """Run a pydantic-ai ``Agent`` against the local Ollama server and return a.

    typed ``LocalAgentResult``.

    This mirrors ``_run_structured_agent`` in ``service.py`` but is self- contained in this
    module so any layer (UI route, service function, or CLI) can call local inference
    without importing the full service graph.

    Parameters ---------- system_prompt: Instruction preamble for the LLM. user_prompt: The
    concrete question or task. result_type: A ``BaseModel`` subclass.  pydantic-ai validates
    the LLM output against this schema and retries automatically on parse failures. config:
    Connection settings.  Defaults to ``LocalLLMConfig.from_env()``. rag_query: If provided,
    the FAISS ``solidworks-api-docs`` namespace is queried with this string and the top
    results are prepended to ``system_prompt`` as grounded API context for the model.  Pass
    the same text as ``user_prompt`` for a simple "augment with API docs" pattern, or a more
    specific sub-query for targeted retrieval. rag_namespace: FAISS namespace to query when
    ``rag_query`` is set.  Defaults to ``"solidworks-api-docs"`` (the COM/VBA surface
    index).

    Returns ------- LocalAgentResult[_T] ``success=True`` with ``data`` set to a validated
    ``result_type`` instance, or ``success=False`` with an ``error`` message.

    Args:
        system_prompt (str): The system prompt value.
        user_prompt (str): The user prompt value.
        result_type (type[_T]): The result type value.
        config (LocalLLMConfig | None): Configuration values for the operation. Defaults to
                                        None.
        rag_query (str | None): The rag query value. Defaults to None.
        rag_namespace (str): The rag namespace value. Defaults to "solidworks-api-docs".

    Returns:
        LocalAgentResult[_T]: The result produced by the operation.
    """
    from ..agents.schemas import RecoverableFailure  # avoid circular at import time

    resolved_config = config or LocalLLMConfig.from_env()

    # --- RAG augmentation ---
    augmented_system_prompt = system_prompt
    if rag_query:
        try:
            from ..agents.vector_rag import (
                query_design_knowledge,
                query_solidworks_api_docs,
            )

            api_context = (
                query_solidworks_api_docs(rag_query)
                if rag_namespace == "solidworks-api-docs"
                else query_design_knowledge(rag_query, namespace=rag_namespace)
            )
            if api_context:
                augmented_system_prompt = f"{system_prompt}\n\n{api_context}"
                logger.debug(
                    "run_local_agent: injected %d RAG chars from '%s'",
                    len(api_context),
                    rag_namespace,
                )
        except Exception as _rag_exc:
            logger.debug("RAG augmentation skipped: %s", _rag_exc)

    try:
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
    except ImportError:  # pragma: no cover
        return LocalAgentResult(
            success=False,
            error="pydantic-ai is not installed in this environment.",
            config=resolved_config,
        )

    model_id = (
        resolved_config.service_model.split(":", 1)[1]
        if resolved_config.service_model.startswith("local:")
        else resolved_config.service_model
    )
    provider = OpenAIProvider(
        base_url=resolved_config.openai_endpoint,
        api_key=resolved_config.api_key,
    )
    configured_model = OpenAIChatModel(model_id, provider=provider)

    agent: Agent[None, _T | RecoverableFailure] = Agent(
        configured_model,
        system_prompt=augmented_system_prompt,
        output_type=[result_type, RecoverableFailure],  # type: ignore[list-item]
    )

    try:
        result = await agent.run(user_prompt)
        payload = result.data if hasattr(result, "data") else result.output
    except Exception as exc:
        logger.exception("run_local_agent failed")
        return LocalAgentResult(
            success=False,
            error=str(exc),
            config=resolved_config,
        )

    if isinstance(payload, RecoverableFailure):
        return LocalAgentResult(
            success=False,
            error=payload.explanation,
            retry_hint=getattr(payload, "retry_hint", None),
            config=resolved_config,
        )

    return LocalAgentResult(success=True, data=payload, config=resolved_config)
