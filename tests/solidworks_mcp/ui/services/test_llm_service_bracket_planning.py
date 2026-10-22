"""Regression tests for explicit feature-order checkpoint generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.ui.services import llm_service


@pytest.mark.asyncio
async def test_inspect_family_enforces_bracket_parity_checkpoint_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit feature-order prompts should produce the exact ordered checkpoint plan."""

    async def _fake_structured_agent(**_kwargs):
        return llm_service.FamilyInspection(
            family="assembly",
            confidence="low",
            evidence=["dummy evidence"],
            warnings=["dummy warning"],
            checkpoints=[
                llm_service.CheckpointCandidate(
                    title="Random plan",
                    allowed_tools=["analyze_geometry"],
                    rationale="placeholder",
                )
            ],
        )

    monkeypatch.setattr(llm_service, "_run_structured_agent", _fake_structured_agent)

    state = await llm_service.inspect_family(
        "bracket-parity-session",
        user_goal=(
            "Create model with exact order Sketch1 -> Base-Extrude-Thin -> "
            "Sketch2 -> Cut-Extrude1 and make Cut-Extrude1 blind 10.0 mm."
        ),
        db_path=tmp_path / "ui.sqlite3",
        model_name="local:gemma4:e2b",
    )

    checkpoint_goals = [item["goal"] for item in state["checkpoints"]]
    assert checkpoint_goals == [
        "Create Sketch1",
        "Create Base-Extrude-Thin",
        "Create Sketch2",
        "Create Cut-Extrude1",
    ]
    assert state["family_confidence"] == "high"
    assert state["proposed_family"] == "extrude"


@pytest.mark.asyncio
async def test_inspect_family_bracket_parity_fallback_on_llm_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit feature-order prompts should still produce exact checkpoints on LLM failure."""

    async def _fake_structured_agent(**_kwargs):
        return llm_service.RecoverableFailure(
            explanation="Model routing failed in test",
            remediation_steps=["switch provider"],
            retry_focus="retry",
            should_retry=True,
        )

    monkeypatch.setattr(llm_service, "_run_structured_agent", _fake_structured_agent)

    state = await llm_service.inspect_family(
        "bracket-parity-fallback",
        user_goal=(
            "Create model with exact order Sketch1 -> Base-Extrude-Thin -> "
            "Sketch2 -> Cut-Extrude1 and make Cut-Extrude1 blind 10.0 mm."
        ),
        db_path=tmp_path / "ui.sqlite3",
        model_name="local:gemma4:e2b",
    )

    checkpoint_goals = [item["goal"] for item in state["checkpoints"]]
    assert checkpoint_goals == [
        "Create Sketch1",
        "Create Base-Extrude-Thin",
        "Create Sketch2",
        "Create Cut-Extrude1",
    ]
    assert state["proposed_family"] == "extrude"
