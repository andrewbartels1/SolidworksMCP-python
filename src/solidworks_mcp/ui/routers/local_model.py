"""Local Ollama model probe / pull / query routes for the Prefab CAD dashboard."""

from __future__ import annotations

from fastapi import APIRouter

from ..local_llm import (
    LocalAgentResult,
    LocalModelProbeResult,
    LocalModelPullRequest,
    LocalModelPullResult,
    LocalModelQueryRequest,
)

router = APIRouter()


@router.get("/api/ui/local-model/probe")
async def probe_local_model_endpoint() -> LocalModelProbeResult:
    """Probe for a running Ollama server and recommend the best Gemma model tier."""
    from ..local_llm import probe_local_model  # noqa: PLC0415

    return await probe_local_model()


@router.post("/api/ui/local-model/pull")
async def pull_local_model_endpoint(
    payload: LocalModelPullRequest,
) -> LocalModelPullResult:
    """Trigger an Ollama pull for the specified model name."""
    from ..local_llm import pull_ollama_model  # noqa: PLC0415

    return await pull_ollama_model(model=payload.model, endpoint=payload.endpoint)


@router.post("/api/ui/local-model/query")
async def query_local_model_endpoint(
    payload: LocalModelQueryRequest,
) -> LocalAgentResult:
    """Run a free-form prompt against the local Ollama model."""
    from pydantic import BaseModel as _BaseModel

    from ..local_llm import LocalLLMConfig, run_local_agent  # noqa: PLC0415

    class _FreeFormResponse(_BaseModel):
        text: str

    config = LocalLLMConfig.from_env()
    if payload.endpoint:
        config = config.model_copy(
            update={
                "endpoint": payload.endpoint,
                "openai_endpoint": f"{payload.endpoint}/v1",
            }
        )
    if payload.model:
        service_model = (
            payload.model
            if payload.model.startswith("local:")
            else f"local:{payload.model}"
        )
        config = config.model_copy(update={"service_model": service_model})

    return await run_local_agent(
        system_prompt=payload.system_prompt,
        user_prompt=payload.prompt,
        result_type=_FreeFormResponse,
        config=config,
    )
