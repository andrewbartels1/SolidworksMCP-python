"""Tests for LLM router endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from solidworks_mcp.ui.routers import llm as llm_router


def test_resolve_user_goal_prefers_session_goal(monkeypatch) -> None:
    """_resolve_user_goal should fall back to session goal when default used."""
    # Ensure the session row is used when user_goal is default.
    monkeypatch.setattr(
        llm_router,
        "get_design_session",
        lambda *_a, **_kw: {"user_goal": "Session goal"},
    )
    resolved = llm_router._resolve_user_goal("s1", llm_router.DEFAULT_USER_GOAL)
    assert resolved == "Session goal"


def test_resolve_user_goal_prefers_payload() -> None:
    """_resolve_user_goal should use explicit user_goal when provided."""
    # Ensure explicit goals pass through untouched.
    resolved = llm_router._resolve_user_goal("s1", "Custom goal")
    assert resolved == "Custom goal"


@pytest.mark.asyncio
async def test_clarify_calls_service(monkeypatch) -> None:
    """clarify should call request_clarifications."""
    # Patch the service call with an async mock.
    monkeypatch.setattr(
        llm_router, "request_clarifications", AsyncMock(return_value={"ok": True})
    )
    payload = llm_router.ClarifyWithAnswerRequest(
        session_id="s1", user_goal="goal", user_answer="answer"
    )
    result = await llm_router.clarify(payload)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_family_inspect_calls_service(monkeypatch) -> None:
    """family_inspect should call inspect_family."""
    # Patch the service call with an async mock.
    monkeypatch.setattr(
        llm_router, "inspect_family", AsyncMock(return_value={"ok": True})
    )
    payload = llm_router.FamilyInspectRequest(session_id="s1", user_goal="goal")
    result = await llm_router.family_inspect(payload)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_orchestrate_go_calls_service(monkeypatch) -> None:
    """orchestrate_go should call run_go_orchestration."""
    # Patch the service call with an async mock.
    monkeypatch.setattr(
        llm_router, "run_go_orchestration", AsyncMock(return_value={"ok": True})
    )
    payload = llm_router.GoOrchestrationRequest(
        session_id="s1",
        user_goal="goal",
        assumptions_text="assume",
        user_answer="answer",
    )
    result = await llm_router.orchestrate_go(payload)
    assert result == {"ok": True}
