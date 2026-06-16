"""Tests for the LLM orchestration helpers."""

from __future__ import annotations

import importlib
import os
import sys
import types
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from solidworks_mcp.ui.services import llm_service


def test_import_handles_missing_pydantic_ai(monkeypatch) -> None:
    """Import should fall back to local RecoverableFailure when missing deps."""
    # Force a fresh import of llm_service with pydantic_ai blocked via sys.modules.
    # Setting sys.modules["pydantic_ai"] = None makes `from pydantic_ai import ...`
    # raise ImportError, triggering the outer except branch.
    monkeypatch.delitem(
        sys.modules, "solidworks_mcp.ui.services.llm_service", raising=False
    )
    monkeypatch.setitem(sys.modules, "pydantic_ai", None)

    fresh = importlib.import_module("solidworks_mcp.ui.services.llm_service")

    assert fresh.Agent is None
    assert fresh.OpenAIChatModel is None
    assert fresh.RecoverableFailure is not None


def test_import_handles_missing_mcp_submodule(monkeypatch) -> None:
    """Import should set MCPServerStreamableHTTP to None when mcp missing."""
    # Force a fresh import with pydantic_ai.mcp blocked — inner try/except fires.
    monkeypatch.delitem(
        sys.modules, "solidworks_mcp.ui.services.llm_service", raising=False
    )
    monkeypatch.setitem(sys.modules, "pydantic_ai.mcp", None)

    fresh = importlib.import_module("solidworks_mcp.ui.services.llm_service")

    assert fresh.MCPServerStreamableHTTP is None


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


def test_extract_explicit_feature_order_regex_no_match() -> None:
    """_extract_explicit_feature_order should return [] when regex finds no match."""
    # The string has "->" but no valid identifier pattern → regex no-match branch (line 146).
    result = llm_service._extract_explicit_feature_order("-> -> ->")
    assert result == []


def test_family_for_feature_order_returns_current_when_no_match() -> None:
    """_family_for_feature_order should return current_family when no keyword matches."""
    # None of assembly, revolve, extrude, cut, sketch in the feature list → line 192.
    result = llm_service._family_for_feature_order(
        ["fillet", "hole", "chamfer"], "loft"
    )
    assert result == "loft"


def test_extract_blind_depth_handles_value_error(monkeypatch) -> None:
    """Value errors during depth parsing should return None."""
    # Force float conversion to fail inside _extract_blind_depth_mm.
    import builtins

    monkeypatch.setattr(
        builtins, "float", lambda _val: (_ for _ in ()).throw(ValueError("bad"))
    )
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
    monkeypatch.setattr(
        llm_service, "_ensure_provider_credentials", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(llm_service, "_build_agent_model", lambda *_a, **_kw: "model")
    monkeypatch.setattr(
        llm_service._inspect,
        "signature",
        lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("bad")),
    )

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
    monkeypatch.setattr(
        llm_service, "_ensure_provider_credentials", lambda *_a, **_kw: None
    )
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
    monkeypatch.setattr(
        llm_service, "_ensure_provider_credentials", lambda *_a, **_kw: None
    )
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

    monkeypatch.setattr(
        session_service, "approve_design_brief", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        session_service, "update_ui_preferences", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    monkeypatch.setattr(
        llm_service, "get_design_session", lambda *_a, **_kw: {"metadata_json": "{}"}
    )
    monkeypatch.setattr(
        llm_service,
        "request_clarifications",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(llm_service, "inspect_family", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        llm_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw)
    )

    result = await llm_service.run_go_orchestration("s1", user_goal="goal")

    assert result == {"ok": True}
    assert any(
        call.get("orchestration_status") == "Go run failed." for call in merge_calls
    )


def test_build_agent_model_local_raises_when_not_installed(monkeypatch) -> None:
    """local: model should raise when OpenAIChatModel or OpenAIProvider is None."""
    # Patch both to None so the guard at the top of the local: branch fires.
    monkeypatch.setattr(llm_service, "OpenAIChatModel", None)
    monkeypatch.setattr(llm_service, "OpenAIProvider", None)
    with pytest.raises(RuntimeError, match="OpenAI provider support is not installed"):
        llm_service._build_agent_model("local:llama3")


def test_build_agent_model_github_raises_when_openai_not_installed(monkeypatch) -> None:
    """github: model should raise when OpenAIChatModel is None."""
    # This covers the OpenAIChatModel is None guard inside the github: branch.
    monkeypatch.setattr(llm_service, "OpenAIChatModel", None)
    with pytest.raises(RuntimeError, match="OpenAI support is not installed"):
        llm_service._build_agent_model("github:openai/gpt-4.1")


@pytest.mark.asyncio
async def test_run_structured_agent_no_toolsets_runs_directly(monkeypatch) -> None:
    """Agent without toolsets should use the simple agent.run path."""

    # MCPServerStreamableHTTP=None → no toolsets → else branch of the if toolsets check.
    class DummyModel(BaseModel):
        value: str

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            return None

        async def run(self, _prompt):
            return types.SimpleNamespace(output={"value": "direct"})

    monkeypatch.setattr(llm_service, "Agent", FakeAgent)
    monkeypatch.setattr(llm_service, "MCPServerStreamableHTTP", None)
    monkeypatch.setattr(
        llm_service, "_ensure_provider_credentials", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(llm_service, "_build_agent_model", lambda *_a, **_kw: "model")

    result = await llm_service._run_structured_agent(
        system_prompt="sys",
        user_prompt="user",
        result_type=DummyModel,
    )
    assert isinstance(result, DummyModel)
    assert result.value == "direct"


@pytest.mark.asyncio
async def test_run_structured_agent_mcp_signature_success(monkeypatch) -> None:
    """MCPServerStreamableHTTP with include_instructions param should set kwargs."""
    # Signature inspection succeeds and include_instructions is in params.
    import inspect as _inspect_mod

    class DummyModel(BaseModel):
        value: str

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def run(self, _prompt):
            return types.SimpleNamespace(output={"value": "ok"})

    class FakeToolset:
        def __init__(self, *_a, **_kw):
            pass

    class _FakeParams:
        def __init__(self):
            self._params = {
                "include_instructions": _inspect_mod.Parameter(
                    "include_instructions", _inspect_mod.Parameter.KEYWORD_ONLY
                )
            }

        @property
        def parameters(self):
            return self._params

    def _fake_signature(_obj):
        return _FakeParams()

    monkeypatch.setattr(llm_service, "Agent", FakeAgent)
    monkeypatch.setattr(llm_service, "MCPServerStreamableHTTP", FakeToolset)
    monkeypatch.setattr(
        llm_service, "_ensure_provider_credentials", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(llm_service, "_build_agent_model", lambda *_a, **_kw: "model")
    monkeypatch.setattr(llm_service._inspect, "signature", lambda _obj: _FakeParams())

    result = await llm_service._run_structured_agent(
        system_prompt="sys",
        user_prompt="user",
        result_type=DummyModel,
    )
    assert isinstance(result, DummyModel)


# ---------------------------------------------------------------------------
# Additional _ensure_provider_credentials branches
# ---------------------------------------------------------------------------


def test_ensure_provider_credentials_github_subprocess_fails(monkeypatch) -> None:
    """GitHub credential missing and gh auth fails should raise RuntimeError."""
    monkeypatch.delenv("GITHUB_API_KEY", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    class _Result:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(llm_service.subprocess, "run", lambda *_a, **_kw: _Result())
    with pytest.raises(RuntimeError, match="GH_TOKEN"):
        llm_service._ensure_provider_credentials("github:openai/gpt-4.1")


def test_ensure_provider_credentials_github_subprocess_raises(monkeypatch) -> None:
    """subprocess.run raising should be caught and credential error raised."""
    monkeypatch.delenv("GITHUB_API_KEY", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    monkeypatch.setattr(
        llm_service.subprocess,
        "run",
        lambda *_a, **_kw: (_ for _ in ()).throw(OSError("no gh")),
    )
    with pytest.raises(RuntimeError, match="GH_TOKEN"):
        llm_service._ensure_provider_credentials("github:openai/gpt-4.1")


def test_ensure_provider_credentials_openai_missing(monkeypatch) -> None:
    """Missing OPENAI_API_KEY should raise RuntimeError."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm_service._ensure_provider_credentials("openai:gpt-4.1")


def test_ensure_provider_credentials_anthropic_missing(monkeypatch) -> None:
    """Missing ANTHROPIC_API_KEY should raise RuntimeError."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm_service._ensure_provider_credentials("anthropic:claude-3")


def test_ensure_provider_credentials_local_no_error(monkeypatch) -> None:
    """local: model should not raise even without credentials."""
    llm_service._ensure_provider_credentials(
        "local:gemma4:e2b", "http://localhost:11434"
    )


def test_ensure_provider_credentials_github_env_already_set(monkeypatch) -> None:
    """When GITHUB_API_KEY is already set, no subprocess is needed."""
    monkeypatch.setenv("GITHUB_API_KEY", "tok123")
    subprocess_calls: list = []
    monkeypatch.setattr(
        llm_service.subprocess, "run", lambda *_a, **_kw: subprocess_calls.append(1)
    )
    llm_service._ensure_provider_credentials("github:openai/gpt-4.1")
    assert not subprocess_calls  # subprocess should NOT be called


# ---------------------------------------------------------------------------
# _resolve_model_name
# ---------------------------------------------------------------------------


def test_resolve_model_name_uses_explicit(monkeypatch) -> None:
    result = llm_service._resolve_model_name("github:openai/gpt-4.1")
    assert result == "github:openai/gpt-4.1"


def test_resolve_model_name_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("SOLIDWORKS_UI_MODEL", "openai:gpt-4o")
    result = llm_service._resolve_model_name(None)
    assert result == "openai:gpt-4o"


def test_resolve_model_name_default_when_no_env(monkeypatch) -> None:
    monkeypatch.delenv("SOLIDWORKS_UI_MODEL", raising=False)
    result = llm_service._resolve_model_name(None)
    assert result == "github:openai/gpt-4.1"


# ---------------------------------------------------------------------------
# _parse_json_blob (module-level helper in llm_service)
# ---------------------------------------------------------------------------


def test_llm_parse_json_blob_valid() -> None:
    assert llm_service._parse_json_blob('{"a": 1}') == {"a": 1}


def test_llm_parse_json_blob_list_returns_empty() -> None:
    assert llm_service._parse_json_blob("[1, 2]") == {}


# ---------------------------------------------------------------------------
# request_clarifications — success and failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_clarifications_recoverable_failure(monkeypatch) -> None:
    """RecoverableFailure from agent should update metadata and return state."""
    from solidworks_mcp.ui.services import session_service

    monkeypatch.setattr(
        session_service, "ensure_dashboard_session", lambda *_a, **_kw: {}
    )
    monkeypatch.setattr(
        llm_service, "get_design_session", lambda *_a, **_kw: {"metadata_json": "{}"}
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    merge_calls: list[dict] = []
    monkeypatch.setattr(
        llm_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw)
    )
    monkeypatch.setattr(llm_service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(
        llm_service,
        "_run_structured_agent",
        AsyncMock(return_value=llm_service.RecoverableFailure(explanation="no model")),
    )

    result = await llm_service.request_clarifications("s1", "make a bracket")
    assert result == {"ok": True}
    assert any("no model" in str(kw) for kw in merge_calls)


@pytest.mark.asyncio
async def test_request_clarifications_success(monkeypatch) -> None:
    """Successful clarification should update metadata with questions."""
    from solidworks_mcp.ui.services import session_service

    monkeypatch.setattr(
        session_service, "ensure_dashboard_session", lambda *_a, **_kw: {}
    )
    monkeypatch.setattr(
        llm_service, "get_design_session", lambda *_a, **_kw: {"metadata_json": "{}"}
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    merge_calls: list[dict] = []
    monkeypatch.setattr(
        llm_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw) or {}
    )
    monkeypatch.setattr(llm_service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(llm_service, "insert_evidence_link", lambda **_kw: None)

    fake_result = llm_service.ClarificationResponse(
        normalized_brief="A mounting bracket for wall use.",
        questions=["What thickness?"],
    )
    monkeypatch.setattr(
        llm_service, "_run_structured_agent", AsyncMock(return_value=fake_result)
    )

    result = await llm_service.request_clarifications("s1", "make a bracket")
    assert result == {"ok": True}
    assert any(
        kw.get("clarifying_questions") == ["What thickness?"] for kw in merge_calls
    )


# ---------------------------------------------------------------------------
# inspect_family — recoverable-failure with feature order fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inspect_family_recoverable_failure_with_feature_order(
    monkeypatch,
) -> None:
    """RecoverableFailure + explicit feature order should trigger coerce fallback."""
    from solidworks_mcp.ui.services import session_service

    monkeypatch.setattr(
        session_service, "ensure_dashboard_session", lambda *_a, **_kw: {}
    )
    monkeypatch.setattr(
        llm_service, "get_design_session", lambda *_a, **_kw: {"metadata_json": "{}"}
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    monkeypatch.setattr(llm_service, "merge_metadata", lambda *_a, **kw: kw or {})
    monkeypatch.setattr(llm_service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(llm_service, "insert_evidence_link", lambda **_kw: None)
    monkeypatch.setattr(llm_service, "replace_plan_checkpoints", lambda **_kw: None)
    monkeypatch.setattr(llm_service, "upsert_design_session", lambda *_a, **_kw: None)

    monkeypatch.setattr(
        llm_service,
        "_run_structured_agent",
        AsyncMock(
            return_value=llm_service.RecoverableFailure(explanation="model down")
        ),
    )

    # Goal with explicit feature order → coerce fallback should fire
    result = await llm_service.inspect_family(
        "s1", "Sketch -> Extrude -> Cut blind 5 mm"
    )
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_inspect_family_recoverable_failure_no_feature_order(monkeypatch) -> None:
    """RecoverableFailure without feature order should update metadata and return state."""
    from solidworks_mcp.ui.services import session_service

    monkeypatch.setattr(
        session_service, "ensure_dashboard_session", lambda *_a, **_kw: {}
    )
    monkeypatch.setattr(
        llm_service, "get_design_session", lambda *_a, **_kw: {"metadata_json": "{}"}
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    merge_calls: list[dict] = []
    monkeypatch.setattr(
        llm_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw) or {}
    )
    monkeypatch.setattr(llm_service, "insert_tool_call_record", lambda **_kw: None)

    monkeypatch.setattr(
        llm_service,
        "_run_structured_agent",
        AsyncMock(
            return_value=llm_service.RecoverableFailure(explanation="model down")
        ),
    )

    result = await llm_service.inspect_family("s1", "make a bracket")
    assert result == {"ok": True}
    assert any("model down" in str(kw) for kw in merge_calls)


@pytest.mark.asyncio
async def test_inspect_family_success_with_checkpoints(monkeypatch) -> None:
    """Successful family inspection should replace checkpoints and persist."""
    from solidworks_mcp.ui.services import session_service

    monkeypatch.setattr(
        session_service, "ensure_dashboard_session", lambda *_a, **_kw: {}
    )
    monkeypatch.setattr(
        llm_service, "get_design_session", lambda *_a, **_kw: {"metadata_json": "{}"}
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    merge_calls: list[dict] = []
    monkeypatch.setattr(
        llm_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw) or {}
    )
    monkeypatch.setattr(llm_service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(llm_service, "insert_evidence_link", lambda **_kw: None)
    replace_calls: list = []
    monkeypatch.setattr(
        llm_service, "replace_plan_checkpoints", lambda **kw: replace_calls.append(kw)
    )
    monkeypatch.setattr(llm_service, "upsert_design_session", lambda *_a, **_kw: None)

    fake_result = llm_service.FamilyInspection(
        family="extrude",
        confidence="high",
        evidence=["Boss-Extrude found"],
        warnings=[],
        checkpoints=[
            llm_service.CheckpointCandidate(
                title="Create sketch",
                allowed_tools=["create_sketch"],
                rationale="Start with sketch",
            )
        ],
    )
    monkeypatch.setattr(
        llm_service, "_run_structured_agent", AsyncMock(return_value=fake_result)
    )

    result = await llm_service.inspect_family("s1", "make a bracket")
    assert result == {"ok": True}
    assert replace_calls  # checkpoints were replaced
