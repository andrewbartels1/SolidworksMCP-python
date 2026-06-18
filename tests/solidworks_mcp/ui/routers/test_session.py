"""Tests for session router endpoints."""

from __future__ import annotations

import pytest

from solidworks_mcp.ui.routers import session as session_router


@pytest.mark.asyncio
async def test_update_notes_calls_service(monkeypatch) -> None:
    """update_notes should call update_session_notes."""
    # Patch the service call to return a sentinel response.
    monkeypatch.setattr(
        session_router, "update_session_notes", lambda *_a, **_kw: {"ok": True}
    )
    payload = session_router.NotesUpdateRequest(session_id="s1", notes_text="notes")
    result = await session_router.update_notes(payload)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_context_save_calls_service(monkeypatch) -> None:
    """context_save should call save_session_context."""
    # Patch the service call to return a sentinel response.
    monkeypatch.setattr(
        session_router, "save_session_context", lambda *_a, **_kw: {"ok": True}
    )
    payload = session_router.ContextSaveRequest(session_id="s1", context_name="ctx")
    result = await session_router.context_save(payload)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_context_load_calls_service(monkeypatch) -> None:
    """context_load should call load_session_context."""
    # Patch the service call to return a sentinel response.
    monkeypatch.setattr(
        session_router, "load_session_context", lambda *_a, **_kw: {"ok": True}
    )
    payload = session_router.ContextLoadRequest(
        session_id="s1", context_file="file.json"
    )
    result = await session_router.context_load(payload)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_get_state_calls_build_dashboard_state(monkeypatch) -> None:
    """get_state should return result of build_dashboard_state."""
    monkeypatch.setattr(
        session_router, "build_dashboard_state", lambda *_a, **_kw: {"session": "s1"}
    )
    result = await session_router.get_state("s1")
    assert result == {"session": "s1"}


@pytest.mark.asyncio
async def test_get_debug_session_calls_trace(monkeypatch) -> None:
    """get_debug_session should return result of build_dashboard_trace_payload."""
    monkeypatch.setattr(
        session_router, "build_dashboard_trace_payload", lambda *_a, **_kw: {"trace": 1}
    )
    result = await session_router.get_debug_session("s1")
    assert result == {"trace": 1}


@pytest.mark.asyncio
async def test_approve_brief_calls_service(monkeypatch) -> None:
    """approve_brief should call approve_design_brief."""
    monkeypatch.setattr(
        session_router, "approve_design_brief", lambda *_a, **_kw: {"approved": True}
    )
    payload = session_router.GoalRequest(session_id="s1", user_goal="test goal")
    result = await session_router.approve_brief(payload)
    assert result == {"approved": True}


@pytest.mark.asyncio
async def test_update_preferences_calls_service(monkeypatch) -> None:
    """update_preferences should call update_ui_preferences."""
    monkeypatch.setattr(
        session_router, "update_ui_preferences", lambda *_a, **_kw: {"prefs": True}
    )
    payload = session_router.PreferencesUpdateRequest(
        session_id="s1", assumptions_text="PETG"
    )
    result = await session_router.update_preferences(payload)
    assert result == {"prefs": True}


@pytest.mark.asyncio
async def test_update_workflow_mode_calls_service(monkeypatch) -> None:
    """update_workflow_mode should call select_workflow_mode."""
    monkeypatch.setattr(
        session_router, "select_workflow_mode", lambda *_a, **_kw: {"mode": "edit"}
    )
    payload = session_router.WorkflowSelectionRequest(
        session_id="s1", workflow_mode="edit_existing"
    )
    result = await session_router.update_workflow_mode(payload)
    assert result == {"mode": "edit"}


@pytest.mark.asyncio
async def test_accept_family_calls_service(monkeypatch) -> None:
    """accept_family should call accept_family_choice."""
    monkeypatch.setattr(
        session_router, "accept_family_choice", lambda *_a, **_kw: {"family": "extrude"}
    )
    payload = session_router.FamilyAcceptRequest(session_id="s1", family="extrude")
    result = await session_router.accept_family(payload)
    assert result == {"family": "extrude"}


@pytest.mark.asyncio
async def test_reconcile_edits_calls_service(monkeypatch) -> None:
    """reconcile_edits should call reconcile_manual_edits."""
    monkeypatch.setattr(
        session_router,
        "reconcile_manual_edits",
        lambda *_a, **_kw: {"reconciled": True},
    )
    payload = session_router.SessionRequest(session_id="s1")
    result = await session_router.reconcile_edits(payload)
    assert result == {"reconciled": True}
