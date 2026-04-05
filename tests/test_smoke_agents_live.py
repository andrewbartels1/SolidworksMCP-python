"""Live smoke tests for agent harness — marked `smoke`, excluded from CI.

These tests make real LLM API calls via GitHub Models (GH_TOKEN) or Anthropic
(ANTHROPIC_API_KEY). They are included in `dev-test-full` but excluded from
CI/CD and the standard `dev-test` run.

Run manually:
    .venv/Scripts/python.exe -m pytest tests/test_smoke_agents_live.py -m smoke -v

Or via dev-commands:
    ./dev-commands.ps1 dev-test-full
"""

from __future__ import annotations

import os
import subprocess

import pytest

from src.solidworks_mcp.agents.harness import run_validated_prompt
from src.solidworks_mcp.agents.schemas import (
    DocsPlan,
    ManufacturabilityReview,
    RecoverableFailure,
)


async def _run_or_skip(**kwargs):
    """Wrap run_validated_prompt and skip the test on 401 auth errors.

    The gh-cli may return an expired or insufficiently-scoped token that passes
    the module-level credential check but is rejected by the GitHub Models API.
    Converting auth errors to pytest.skip keeps dev-test-full green while
    still exercising the harness when valid credentials are present.
    """
    from pydantic_ai.exceptions import ModelHTTPError

    try:
        return await run_validated_prompt(**kwargs)
    except ModelHTTPError as exc:
        if exc.status_code == 401:
            pytest.skip(
                f"LLM credentials rejected with 401 — refresh GH_TOKEN or provide ANTHROPIC_API_KEY"
            )
        raise


# ---------------------------------------------------------------------------
# Skip guard — skip entire module if no credentials are available
# ---------------------------------------------------------------------------


def _resolve_github_token() -> str | None:
    token = os.getenv("GITHUB_API_KEY") or os.getenv("GH_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


_GH_TOKEN = _resolve_github_token()
_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

_skip_no_credentials = pytest.mark.skipif(
    not _GH_TOKEN and not _ANTHROPIC_KEY,
    reason="No LLM credentials available (GH_TOKEN, GITHUB_API_KEY, or ANTHROPIC_API_KEY required)",
)


def _set_github_env() -> str:
    """Ensure GITHUB_API_KEY is set and return the model string."""
    if _GH_TOKEN:
        os.environ.setdefault("GITHUB_API_KEY", _GH_TOKEN)
        return "github:openai/gpt-4.1"
    raise RuntimeError("No GitHub token available")


# ---------------------------------------------------------------------------
# Live tests — all marked `smoke` so CI never runs them
# ---------------------------------------------------------------------------


@pytest.mark.smoke
@_skip_no_credentials
@pytest.mark.asyncio
async def test_print_architect_manufacturability(tmp_path):
    """solidworks-print-architect returns a valid ManufacturabilityReview."""
    model = _set_github_env()
    db = tmp_path / "live_test.sqlite3"

    result = await _run_or_skip(
        agent_file_name="solidworks-print-architect.agent.md",
        model_name=model,
        user_prompt=(
            "Design a PLA snap-fit battery cover for a 220x220x250 bed. "
            "Give tolerance and orientation guidance."
        ),
        result_type=ManufacturabilityReview,
        max_retries_on_recoverable=1,
        db_path=db,
    )

    assert not isinstance(result, RecoverableFailure), (
        f"Agent returned RecoverableFailure: {result.explanation}"
    )
    assert isinstance(result, ManufacturabilityReview)
    assert len(result.summary) >= 10
    assert result.orientation_guidance
    assert result.build_volume_check


@pytest.mark.smoke
@_skip_no_credentials
@pytest.mark.asyncio
async def test_mcp_skill_docs_schema(tmp_path):
    """solidworks-mcp-skill-docs returns a valid DocsPlan."""
    model = _set_github_env()
    db = tmp_path / "live_test_docs.sqlite3"

    result = await _run_or_skip(
        agent_file_name="solidworks-mcp-skill-docs.agent.md",
        model_name=model,
        user_prompt=(
            "Plan a tutorial page showing how to create a bracket "
            "in SolidWorks using the MCP server tools."
        ),
        result_type=DocsPlan,
        max_retries_on_recoverable=1,
        db_path=db,
    )

    assert not isinstance(result, RecoverableFailure), (
        f"Agent returned RecoverableFailure: {result.explanation}"
    )
    assert isinstance(result, DocsPlan)
    assert result.audience
    assert result.objective


@pytest.mark.smoke
@_skip_no_credentials
@pytest.mark.asyncio
async def test_research_validator_manufacturability(tmp_path):
    """solidworks-research-validator returns a valid ManufacturabilityReview."""
    model = _set_github_env()
    db = tmp_path / "live_test_validator.sqlite3"

    result = await _run_or_skip(
        agent_file_name="solidworks-research-validator.agent.md",
        model_name=model,
        user_prompt=(
            "Verify UV-stabilized PETG guidance for an outdoor FDM/FFF enclosure "
            "that sees up to 55 C service temperature and about 8 hours of direct "
            "sun per day. Provide heat resistance, UV stability, and recommended "
            "wall thickness guidance."
        ),
        result_type=ManufacturabilityReview,
        max_retries_on_recoverable=1,
        db_path=db,
    )

    assert not isinstance(result, RecoverableFailure), (
        f"Agent returned RecoverableFailure: {result.explanation}"
    )
    assert isinstance(result, ManufacturabilityReview)


@pytest.mark.smoke
@_skip_no_credentials
@pytest.mark.asyncio
async def test_print_architect_docs_schema(tmp_path):
    """solidworks-print-architect can also produce a valid DocsPlan."""
    model = _set_github_env()
    db = tmp_path / "live_test_docs2.sqlite3"

    result = await _run_or_skip(
        agent_file_name="solidworks-print-architect.agent.md",
        model_name=model,
        user_prompt=(
            "Plan a tutorial page for designing a 3D printed hinge "
            "in SolidWorks with correct tolerances."
        ),
        result_type=DocsPlan,
        max_retries_on_recoverable=1,
        db_path=db,
    )

    assert not isinstance(result, RecoverableFailure), (
        f"Agent returned RecoverableFailure: {result.explanation}"
    )
    assert isinstance(result, DocsPlan)


@pytest.mark.smoke
@_skip_no_credentials
@pytest.mark.asyncio
async def test_results_persisted_to_sqlite(tmp_path):
    """Successful live run writes an agent_run record to SQLite."""
    model = _set_github_env()
    db = tmp_path / "persist_test.sqlite3"

    await _run_or_skip(
        agent_file_name="solidworks-print-architect.agent.md",
        model_name=model,
        user_prompt="Design a simple ABS bracket for a 250x210 bed.",
        result_type=ManufacturabilityReview,
        max_retries_on_recoverable=1,
        db_path=db,
    )

    from sqlmodel import Session, create_engine, select
    from src.solidworks_mcp.agents.history_db import AgentRun, init_db

    init_db(db)
    engine = create_engine(f"sqlite:///{db}")
    with Session(engine) as session:
        runs = session.exec(select(AgentRun)).all()
    engine.dispose()

    assert len(runs) >= 1
    assert any(r.status == "success" for r in runs)
