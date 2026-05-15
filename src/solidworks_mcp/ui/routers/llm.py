"""LLM clarify / inspect / go-orchestration routes for the Prefab CAD dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ...agents.history_db import get_design_session
from ..services import (
    DEFAULT_SESSION_ID,
    DEFAULT_USER_GOAL,
    inspect_family,
    request_clarifications,
    run_go_orchestration,
)

router = APIRouter()


def _resolve_user_goal(session_id: str, user_goal: str) -> str:
    """Prefer the approved session goal when the client sends the default placeholder."""

    if user_goal and user_goal != DEFAULT_USER_GOAL:
        return user_goal

    session_row = get_design_session(session_id) or {}
    return str(session_row.get("user_goal") or DEFAULT_USER_GOAL)


class ClarifyWithAnswerRequest(BaseModel):
    """Request payload for clarify that includes the user's typed answers."""

    session_id: str = DEFAULT_SESSION_ID
    user_goal: str = DEFAULT_USER_GOAL
    user_answer: str = ""


class GoOrchestrationRequest(BaseModel):
    """Request payload for global Go orchestration action."""

    session_id: str = DEFAULT_SESSION_ID
    user_goal: str = DEFAULT_USER_GOAL
    assumptions_text: str | None = None
    user_answer: str = ""


class FamilyInspectRequest(BaseModel):
    """Request payload for design family classification."""

    session_id: str = DEFAULT_SESSION_ID
    user_goal: str = DEFAULT_USER_GOAL


@router.post("/api/ui/clarify")
async def clarify(payload: ClarifyWithAnswerRequest) -> dict[str, Any]:
    """Call the LLM to generate clarifying questions for the design goal."""
    return await request_clarifications(
        payload.session_id,
        user_goal=_resolve_user_goal(payload.session_id, payload.user_goal),
        user_answer=payload.user_answer,
    )


@router.post("/api/ui/family/inspect")
async def family_inspect(payload: FamilyInspectRequest) -> dict[str, Any]:
    """Call the LLM to classify the design family from the current goal."""
    return await inspect_family(
        payload.session_id,
        user_goal=_resolve_user_goal(payload.session_id, payload.user_goal),
    )


@router.post("/api/ui/orchestrate/go")
async def orchestrate_go(payload: GoOrchestrationRequest) -> dict[str, Any]:
    """Run the full Go orchestration pipeline (clarify → inspect → plan checkpoints)."""
    return await run_go_orchestration(
        payload.session_id,
        user_goal=_resolve_user_goal(payload.session_id, payload.user_goal),
        assumptions_text=payload.assumptions_text,
        user_answer=payload.user_answer,
    )
