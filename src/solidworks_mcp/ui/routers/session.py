"""Session management routes for the Prefab CAD dashboard.

Covers: state hydration, debug snapshot, brief approval, preferences,
workflow selection, notes, context save/load, family accept, and manual-sync reconcile.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..services import (
    DEFAULT_API_ORIGIN,
    DEFAULT_SESSION_ID,
    DEFAULT_USER_GOAL,
    accept_family_choice,
    approve_design_brief,
    build_dashboard_state,
    build_dashboard_trace_payload,
    load_session_context,
    reconcile_manual_edits,
    save_session_context,
    select_workflow_mode,
    update_session_notes,
    update_ui_preferences,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SessionRequest(BaseModel):
    """Base request payload containing session scope."""

    session_id: str = DEFAULT_SESSION_ID


class GoalRequest(SessionRequest):
    """Request payload for endpoints that operate on the current design goal."""

    user_goal: str = DEFAULT_USER_GOAL


class FamilyAcceptRequest(SessionRequest):
    """Request payload for family acceptance."""

    family: str | None = None


class PreferencesUpdateRequest(SessionRequest):
    """Request payload for assumptions and model preference updates."""

    assumptions_text: str
    model_provider: str = "github"
    model_profile: str = "balanced"
    model_name: str | None = None
    local_endpoint: str | None = None


class WorkflowSelectionRequest(SessionRequest):
    """Request payload for selecting the onboarding workflow branch."""

    workflow_mode: str


class NotesUpdateRequest(SessionRequest):
    """Request payload for saving free-form engineering notes."""

    notes_text: str = ""


class ContextSaveRequest(SessionRequest):
    """Request payload for saving context to a plain JSON snapshot."""

    context_name: str | None = None


class ContextLoadRequest(SessionRequest):
    """Request payload for loading context snapshot from plain JSON."""

    context_file: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/api/ui/state")
async def get_state(session_id: str = Query(DEFAULT_SESSION_ID)) -> dict[str, Any]:
    """Hydrate UI state from active session database."""
    return build_dashboard_state(session_id, api_origin=DEFAULT_API_ORIGIN)


@router.get("/api/ui/debug/session")
async def get_debug_session(
    session_id: str = Query(DEFAULT_SESSION_ID),
) -> dict[str, Any]:
    """Return a verbose debug snapshot for the active UI session."""
    return build_dashboard_trace_payload(session_id, api_origin=DEFAULT_API_ORIGIN)


@router.post("/api/ui/brief/approve")
async def approve_brief(payload: GoalRequest) -> dict[str, Any]:
    """Accept the user-provided design goal."""
    return approve_design_brief(payload.session_id, payload.user_goal)


@router.post("/api/ui/preferences/update")
async def update_preferences(payload: PreferencesUpdateRequest) -> dict[str, Any]:
    """Persist assumptions and provider/model preferences in session metadata."""
    return update_ui_preferences(
        payload.session_id,
        assumptions_text=payload.assumptions_text,
        model_provider=payload.model_provider,
        model_profile=payload.model_profile,
        model_name=payload.model_name,
        local_endpoint=payload.local_endpoint,
    )


@router.post("/api/ui/workflow/select")
async def update_workflow_mode(payload: WorkflowSelectionRequest) -> dict[str, Any]:
    """Persist the workflow choice shown on the opening dashboard screen."""
    return select_workflow_mode(payload.session_id, workflow_mode=payload.workflow_mode)


@router.post("/api/ui/family/accept")
async def accept_family(payload: FamilyAcceptRequest) -> dict[str, Any]:
    """Accept the proposed design family classification."""
    return accept_family_choice(payload.session_id, family=payload.family)


@router.post("/api/ui/notes/update")
async def update_notes(payload: NotesUpdateRequest) -> dict[str, Any]:
    """Persist free-form engineering notes for the session."""
    return update_session_notes(payload.session_id, notes_text=payload.notes_text)


@router.post("/api/ui/context/save")
async def context_save(payload: ContextSaveRequest) -> dict[str, Any]:
    """Save current session context to a JSON snapshot file."""
    return save_session_context(payload.session_id, context_name=payload.context_name)


@router.post("/api/ui/context/load")
async def context_load(payload: ContextLoadRequest) -> dict[str, Any]:
    """Load a previously saved session context JSON snapshot."""
    return load_session_context(payload.session_id, context_file=payload.context_file)


@router.post("/api/ui/manual-sync/reconcile")
async def reconcile_edits(payload: SessionRequest) -> dict[str, Any]:
    """Detect manual edits via snapshot diff and apply forward delta."""
    return reconcile_manual_edits(payload.session_id)
