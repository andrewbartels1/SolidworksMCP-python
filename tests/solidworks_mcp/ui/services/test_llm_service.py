"""Tests for the LLM orchestration helpers."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest
from pydantic import BaseModel

from solidworks_mcp.ui.services import llm_service


def _load_llm_service_alias(monkeypatch, *, with_mcp: bool) -> types.ModuleType:
    """Load llm_service under an alias with stubbed pydantic_ai modules."""
    fake = types.ModuleType("pydantic_ai")
    fake.Agent = object
    fake.RecoverableFailure = type("RecoverableFailure", (BaseModel,), {})

    models = types.ModuleType("pydantic_ai.models")
    models_openai = types.ModuleType("pydantic_ai.models.openai")
    models_openai.OpenAIChatModel = object
    providers = types.ModuleType("pydantic_ai.providers")
    providers_openai = types.ModuleType("pydantic_ai.providers.openai")
    providers_openai.OpenAIProvider = object

    monkeypatch.setitem(sys.modules, "pydantic_ai", fake)
    monkeypatch.setitem(sys.modules, "pydantic_ai.models", models)
    monkeypatch.setitem(sys.modules, "pydantic_ai.models.openai", models_openai)
    monkeypatch.setitem(sys.modules, "pydantic_ai.providers", providers)
    monkeypatch.setitem(sys.modules, "pydantic_ai.providers.openai", providers_openai)

    if with_mcp:
        mcp = types.ModuleType("pydantic_ai.mcp")
        mcp.MCPServerStreamableHTTP = object
        monkeypatch.setitem(sys.modules, "pydantic_ai.mcp", mcp)

    module_path = Path(__file__).parents[3] / "src" / "solidworks_mcp" / "ui" / "services" / "llm_service.py"
    spec = importlib.util.spec_from_file_location("llm_service_alias", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_handles_missing_pydantic_ai(monkeypatch) -> None:
    """Import should fall back to local RecoverableFailure when missing deps."""
    # Force import to fail for pydantic_ai and assert fallback class is created.
    import builtins

    original_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name.startswith("pydantic_ai"):
            raise ImportError("blocked")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    module_path = Path(__file__).parents[3] / "src" / "solidworks_mcp" / "ui" / "services" / "llm_service.py"
    spec = importlib.util.spec_from_file_location("llm_service_no_ai", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.Agent is None
    assert module.OpenAIChatModel is None
    assert module.RecoverableFailure is not None


def test_import_handles_missing_mcp_submodule(monkeypatch) -> None:
    """Import should set MCPServerStreamableHTTP to None when mcp missing."""
    # Load llm_service with a fake pydantic_ai that lacks the mcp submodule.
    module = _load_llm_service_alias(monkeypatch, with_mcp=False)
    assert module.MCPServerStreamableHTTP is None


def test_parse_json_blob_variants() -> None:
    """_parse_json_blob should handle empty and invalid JSON gracefully."""
    # Cover empty, invalid, list, and dict payload handling.
    assert llm_service._parse_json_blob(None) == {}
    assert llm_service._parse_json_blob("not-json") == {}
    assert llm_service._parse_json_blob('["list"]') == {}
    assert llm_service._parse_json_blob('{"ok": true}') == {"ok": True}


def test_feature_helpers_and_coerce_plan() -> None:
    """Explicit feature ordering should coerce the checkpoint plan."""
    # Cover explicit order extraction and checkpoint coercion.
    ordered = llm_service._extract_explicit_feature_order("Sketch -> Extrude -> Cut")
    assert ordered == ["Sketch", "Extrude", "Cut"]
    assert llm_service._extract_explicit_feature_order("no arrows") == []

    assert llm_service._extract_blind_depth_mm("blind 10.0 mm") == 10.0
    assert llm_service._extract_blind_depth_mm("no depth here") is None

    assert llm_service._tools_for_feature_name("First Sketch", 1) == [
        "create_sketch",
        "add_line",
        "exit_sketch",
    ]
    assert llm_service._tools_for_feature_name("Sketch", 2) == [
        "create_sketch",
        "add_circle",
        "exit_sketch",
    ]
    assert llm_service._tools_for_feature_name("Cut", 1) == ["create_cut"]
    assert llm_service._tools_for_feature_name("Revolve", 1) == ["create_revolve"]
    assert llm_service._tools_for_feature_name("Extrude", 1) == ["create_extrusion"]
    assert llm_service._tools_for_feature_name("Unknown", 1) == ["analyze_geometry"]

    assert llm_service._family_for_feature_order(["assembly"], "extrude") == "assembly"
    assert llm_service._family_for_feature_order(["revolve"], "extrude") == "revolve"
    assert llm_service._family_for_feature_order(["sketch"], "revolve") == "extrude"

    result = llm_service.FamilyInspection(
        family="extrude",
        confidence="low",
        evidence=[],
        warnings=[],
        checkpoints=[],
    )
    coerced = llm_service._coerce_explicit_feature_order_plan(
        "Sketch -> Extrude -> Cut blind 5 mm",
        result,
    )
    assert coerced.family == "extrude"
    assert len(coerced.checkpoints) == 3
    assert coerced.confidence in {"low", "high"}


def test_extract_blind_depth_handles_value_error(monkeypatch) -> None:
    """Value errors during depth parsing should return None."""
    # Force float conversion to fail inside _extract_blind_depth_mm.
    import builtins

    monkeypatch.setattr(builtins, "float", lambda _val: (_ for _ in ()).throw(ValueError("bad")))
    assert llm_service._extract_blind_depth_mm("blind 10.0 mm") is None


def test_ensure_provider_credentials_sets_github_from_subprocess(monkeypatch) -> None:
    """GitHub credentials should be sourced from gh auth token."""
    # Ensure the subprocess fallback sets GITHUB_API_KEY.
    monkeypatch.delenv("GITHUB_API_KEY", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    class _Result:
        returncode = 0
        stdout = "token"

    monkeypatch.setattr(llm_service.subprocess, "run", lambda *_a, **_kw: _Result())
    llm_service._ensure_provider_credentials("github:openai/gpt-4.1")
    assert os.environ.get("GITHUB_API_KEY") == "token"


def test_build_agent_model_github_import_error(monkeypatch) -> None:
    """Missing GitHubProvider should raise RuntimeError."""
    # Force the GitHubProvider import to fail.
    monkeypatch.setattr(llm_service, "OpenAIChatModel", object)

    import builtins

    original_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == "pydantic_ai.providers.github":
            raise ImportError("no github provider")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    with pytest.raises(RuntimeError, match="GitHubProvider"):
        llm_service._build_agent_model("github:openai/gpt-4.1")


def test_build_agent_model_returns_raw_model() -> None:
    """Non-local/github model names should pass through unchanged."""
    # Validate the passthrough branch in _build_agent_model.
    assert llm_service._build_agent_model("openai:gpt-4.1") == "openai:gpt-4.1"


@pytest.mark.asyncio
async def test_run_structured_agent_toolset_fallback(monkeypatch) -> None:
    """Toolset failures should fall back to a planning-only run."""
    # Force toolset run to fail and verify fallback agent is used.
    class DummyModel(BaseModel):
        value: str

    class FakeAgent:
        calls = 0

        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def run(self, _prompt):
            FakeAgent.calls += 1
            if FakeAgent.calls == 1:
                raise RuntimeError("toolset fail")
            return types.SimpleNamespace(output={"value": "ok"})

    monkeypatch.setattr(llm_service, "Agent", FakeAgent)
    class FakeToolset:
        def __init__(self, *_a, **_kw):
            return None

    monkeypatch.setattr(llm_service, "MCPServerStreamableHTTP", FakeToolset)
    monkeypatch.setattr(llm_service, "_ensure_provider_credentials", lambda *_a, **_kw: None)
    monkeypatch.setattr(llm_service, "_build_agent_model", lambda *_a, **_kw: "model")
    monkeypatch.setattr(llm_service._inspect, "signature", lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("bad")))

    result = await llm_service._run_structured_agent(
        system_prompt="sys",
        user_prompt="user",
        result_type=DummyModel,
        model_name="github:openai/gpt-4.1",
    )
    assert isinstance(result, DummyModel)
    assert result.value == "ok"


@pytest.mark.asyncio
async def test_run_structured_agent_returns_recoverable_failure(monkeypatch) -> None:
    """RecoverableFailure payloads should pass through."""
    # Ensure RecoverableFailure data is returned directly.
    class DummyModel(BaseModel):
        value: str

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            return None

        async def run(self, _prompt):
            return types.SimpleNamespace(
                output=llm_service.RecoverableFailure(explanation="fail"),
            )

    monkeypatch.setattr(llm_service, "Agent", FakeAgent)
    monkeypatch.setattr(llm_service, "MCPServerStreamableHTTP", None)
    monkeypatch.setattr(llm_service, "_ensure_provider_credentials", lambda *_a, **_kw: None)
    monkeypatch.setattr(llm_service, "_build_agent_model", lambda *_a, **_kw: "model")

    result = await llm_service._run_structured_agent(
        system_prompt="sys",
        user_prompt="user",
        result_type=DummyModel,
    )
    assert isinstance(result, llm_service.RecoverableFailure)


@pytest.mark.asyncio
async def test_run_structured_agent_handles_agent_exception(monkeypatch) -> None:
    """Agent exceptions should return a RecoverableFailure."""
    # Ensure failures in agent.run are wrapped as RecoverableFailure.
    class DummyModel(BaseModel):
        value: str

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            return None

        async def run(self, _prompt):
            raise RuntimeError("boom")

    monkeypatch.setattr(llm_service, "Agent", FakeAgent)
    monkeypatch.setattr(llm_service, "MCPServerStreamableHTTP", None)
    monkeypatch.setattr(llm_service, "_ensure_provider_credentials", lambda *_a, **_kw: None)
    monkeypatch.setattr(llm_service, "_build_agent_model", lambda *_a, **_kw: "model")

    result = await llm_service._run_structured_agent(
        system_prompt="sys",
        user_prompt="user",
        result_type=DummyModel,
    )
    assert isinstance(result, llm_service.RecoverableFailure)
    assert "Model routing failed" in result.explanation


@pytest.mark.asyncio
async def test_run_go_orchestration_error_path(monkeypatch) -> None:
    """run_go_orchestration should handle failures with metadata updates."""
    # Trigger an exception inside Go orchestration and assert merge_metadata call.
    from solidworks_mcp.ui.services import session_service

    merge_calls: list[dict[str, object]] = []

    monkeypatch.setattr(session_service, "approve_design_brief", lambda *_a, **_kw: None)
    monkeypatch.setattr(session_service, "update_ui_preferences", lambda *_a, **_kw: None)
    monkeypatch.setattr(session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(llm_service, "get_design_session", lambda *_a, **_kw: {"metadata_json": "{}"})
    monkeypatch.setattr(llm_service, "request_clarifications", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(llm_service, "inspect_family", lambda *_a, **_kw: None)
    monkeypatch.setattr(llm_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw))

    result = await llm_service.run_go_orchestration("s1", user_goal="goal")

    assert result == {"ok": True}
    assert any(call.get("orchestration_status") == "Go run failed." for call in merge_calls)
