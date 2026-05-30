"""Tests for session router endpoints."""

from __future__ import annotations

import pytest

from solidworks_mcp.ui.routers import session as session_router


@pytest.mark.asyncio
async def test_update_notes_calls_service(monkeypatch) -> None:
    """update_notes should call update_session_notes."""
    # Patch the service call to return a sentinel response.
    monkeypatch.setattr(session_router, "update_session_notes", lambda *_a, **_kw: {"ok": True})
    payload = session_router.NotesUpdateRequest(session_id="s1", notes_text="notes")
    result = await session_router.update_notes(payload)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_context_save_calls_service(monkeypatch) -> None:
    """context_save should call save_session_context."""
    # Patch the service call to return a sentinel response.
    monkeypatch.setattr(session_router, "save_session_context", lambda *_a, **_kw: {"ok": True})
    payload = session_router.ContextSaveRequest(session_id="s1", context_name="ctx")
    result = await session_router.context_save(payload)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_context_load_calls_service(monkeypatch) -> None:
    """context_load should call load_session_context."""
    # Patch the service call to return a sentinel response.
    monkeypatch.setattr(session_router, "load_session_context", lambda *_a, **_kw: {"ok": True})
    payload = session_router.ContextLoadRequest(session_id="s1", context_file="file.json")
    result = await session_router.context_load(payload)
    assert result == {"ok": True}
