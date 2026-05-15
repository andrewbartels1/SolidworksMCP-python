"""Checkpoint execution route for the Prefab CAD dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import DEFAULT_SESSION_ID, execute_next_checkpoint

router = APIRouter()


class CheckpointExecuteRequest(BaseModel):
    """Request payload for checkpoint execution."""

    session_id: str = DEFAULT_SESSION_ID


@router.post("/api/ui/checkpoints/execute-next")
async def execute_checkpoint(payload: CheckpointExecuteRequest) -> dict[str, Any]:
    """Execute the next pending design checkpoint against the SolidWorks adapter."""
    return await execute_next_checkpoint(payload.session_id)
