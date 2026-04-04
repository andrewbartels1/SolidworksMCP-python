"""Tests for src/solidworks_mcp/agents/harness.py — targeting 100% coverage."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.solidworks_mcp.agents.harness import (
    _extract_data,
    _load_agent_prompt,
    pretty_json,
    run_validated_prompt,
)
from src.solidworks_mcp.agents.schemas import (
    ManufacturabilityReview,
    RecoverableFailure,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def agent_file(tmp_path: Path) -> Path:
    """Write a minimal agent file with YAML frontmatter."""
    agents_dir = tmp_path / ".github" / "agents"
    agents_dir.mkdir(parents=True)
    content = (
        "---\n"
        "name: Test Agent\n"
        "description: Used in tests.\n"
        "---\n"
        "You are a test agent. Respond with structured output.\n"
    )
    path = agents_dir / "test-agent.agent.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def agent_file_no_frontmatter(tmp_path: Path) -> Path:
    agents_dir = tmp_path / ".github" / "agents"
    agents_dir.mkdir(parents=True)
    path = agents_dir / "raw-agent.agent.md"
    path.write_text("You are a raw agent.", encoding="utf-8")
    return path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_harness.sqlite3"


@pytest.fixture
def valid_review() -> ManufacturabilityReview:
    return ManufacturabilityReview(
        summary="A sufficient summary for testing.",
        orientation_guidance="Print flat on bed.",
        build_volume_check="Fits within envelope.",
    )


@pytest.fixture
def recoverable_failure() -> RecoverableFailure:
    return RecoverableFailure(
        explanation="Schema validation failed here.",
        remediation_steps=["Narrow the prompt"],
        retry_focus="Focus on material only.",
        should_retry=True,
    )


# ---------------------------------------------------------------------------
# _load_agent_prompt
# ---------------------------------------------------------------------------


class TestLoadAgentPrompt:
    def test_strips_yaml_frontmatter(self, agent_file: Path, monkeypatch):
        monkeypatch.chdir(agent_file.parent.parent.parent)
        prompt = _load_agent_prompt("test-agent.agent.md")
        assert "You are a test agent." in prompt
        assert "---" not in prompt
        assert "name: Test Agent" not in prompt

    def test_returns_raw_when_no_frontmatter(self, agent_file_no_frontmatter: Path, monkeypatch):
        monkeypatch.chdir(agent_file_no_frontmatter.parent.parent.parent)
        prompt = _load_agent_prompt("raw-agent.agent.md")
        assert prompt == "You are a raw agent."

    def test_strips_leading_trailing_whitespace(self, tmp_path: Path, monkeypatch):
        agents_dir = tmp_path / ".github" / "agents"
        agents_dir.mkdir(parents=True)
        path = agents_dir / "spaced-agent.agent.md"
        path.write_text(
            "---\nname: X\n---\n\n\n  You are spaced.  \n\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        prompt = _load_agent_prompt("spaced-agent.agent.md")
        assert prompt == "You are spaced."


# ---------------------------------------------------------------------------
# _extract_data
# ---------------------------------------------------------------------------


class TestExtractData:
    def test_returns_data_attribute_when_present(self):
        obj = SimpleNamespace(data="the_data")
        assert _extract_data(obj) == "the_data"

    def test_returns_output_attribute_when_no_data(self):
        obj = SimpleNamespace(output="the_output")
        assert _extract_data(obj) == "the_output"

    def test_returns_value_when_neither_attribute(self):
        assert _extract_data("plain_string") == "plain_string"
        assert _extract_data(42) == 42

    def test_data_takes_precedence_over_output(self):
        obj = SimpleNamespace(data="data_val", output="output_val")
        assert _extract_data(obj) == "data_val"


# ---------------------------------------------------------------------------
# pretty_json
# ---------------------------------------------------------------------------


class TestPrettyJson:
    def test_returns_valid_json(self, valid_review: ManufacturabilityReview):
        output = pretty_json(valid_review)
        parsed = json.loads(output)
        assert parsed["summary"] == valid_review.summary

    def test_is_indented(self, valid_review: ManufacturabilityReview):
        output = pretty_json(valid_review)
        assert "\n" in output  # indented JSON has newlines

    def test_works_for_recoverable_failure(self, recoverable_failure: RecoverableFailure):
        output = pretty_json(recoverable_failure)
        parsed = json.loads(output)
        assert "explanation" in parsed


# ---------------------------------------------------------------------------
# run_validated_prompt — success path
# ---------------------------------------------------------------------------


class TestRunValidatedPromptSuccess:
    @pytest.mark.asyncio
    async def test_returns_validated_model(
        self, agent_file: Path, db_path: Path, valid_review: ManufacturabilityReview, monkeypatch
    ):
        monkeypatch.chdir(agent_file.parent.parent.parent)

        mock_result = SimpleNamespace(data=valid_review)
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_agent_cls = MagicMock(return_value=mock_agent)

        with patch("src.solidworks_mcp.agents.harness.Agent", mock_agent_cls):
            result = await run_validated_prompt(
                agent_file_name="test-agent.agent.md",
                model_name="github:openai/gpt-4.1",
                user_prompt="Design a snap-fit cover.",
                result_type=ManufacturabilityReview,
                db_path=db_path,
            )

        assert isinstance(result, ManufacturabilityReview)
        assert result.summary == valid_review.summary

    @pytest.mark.asyncio
    async def test_persists_success_run(
        self, agent_file: Path, db_path: Path, valid_review: ManufacturabilityReview, monkeypatch
    ):
        monkeypatch.chdir(agent_file.parent.parent.parent)

        mock_result = SimpleNamespace(data=valid_review)
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch("src.solidworks_mcp.agents.harness.Agent", MagicMock(return_value=mock_agent)):
            await run_validated_prompt(
                agent_file_name="test-agent.agent.md",
                model_name="github:openai/gpt-4.1",
                user_prompt="Test prompt.",
                result_type=ManufacturabilityReview,
                db_path=db_path,
            )

        from src.solidworks_mcp.agents.history_db import find_recent_errors, init_db
        from sqlmodel import Session, create_engine, select
        from src.solidworks_mcp.agents.history_db import AgentRun

        init_db(db_path)
        engine = create_engine(f"sqlite:///{db_path}")
        with Session(engine) as session:
            runs = session.exec(select(AgentRun)).all()
        engine.dispose()
        assert len(runs) == 1
        assert runs[0].status == "success"

    @pytest.mark.asyncio
    async def test_uses_output_attribute_fallback(
        self, agent_file: Path, db_path: Path, valid_review: ManufacturabilityReview, monkeypatch
    ):
        """Covers the _extract_data output-attribute branch in run_validated_prompt."""
        monkeypatch.chdir(agent_file.parent.parent.parent)

        mock_result = SimpleNamespace(output=valid_review)  # no .data, only .output
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch("src.solidworks_mcp.agents.harness.Agent", MagicMock(return_value=mock_agent)):
            result = await run_validated_prompt(
                agent_file_name="test-agent.agent.md",
                model_name="github:openai/gpt-4.1",
                user_prompt="Test.",
                result_type=ManufacturabilityReview,
                db_path=db_path,
            )

        assert isinstance(result, ManufacturabilityReview)

    @pytest.mark.asyncio
    async def test_validates_dict_payload(
        self, agent_file: Path, db_path: Path, monkeypatch
    ):
        """Covers the model_validate branch when payload is a dict, not a model instance."""
        monkeypatch.chdir(agent_file.parent.parent.parent)

        raw_dict = ManufacturabilityReview(
            summary="Dict payload summary here.",
            orientation_guidance="Flat on bed.",
            build_volume_check="Fits envelope.",
        ).model_dump()

        mock_result = SimpleNamespace(data=raw_dict)
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch("src.solidworks_mcp.agents.harness.Agent", MagicMock(return_value=mock_agent)):
            result = await run_validated_prompt(
                agent_file_name="test-agent.agent.md",
                model_name="github:openai/gpt-4.1",
                user_prompt="Test.",
                result_type=ManufacturabilityReview,
                db_path=db_path,
            )

        assert isinstance(result, ManufacturabilityReview)


# ---------------------------------------------------------------------------
# run_validated_prompt — RecoverableFailure paths
# ---------------------------------------------------------------------------


class TestRunValidatedPromptRecoverable:
    @pytest.mark.asyncio
    async def test_returns_recoverable_failure_when_no_retry(
        self, agent_file: Path, db_path: Path, recoverable_failure: RecoverableFailure, monkeypatch
    ):
        monkeypatch.chdir(agent_file.parent.parent.parent)
        recoverable_failure.should_retry = False

        mock_result = SimpleNamespace(data=recoverable_failure)
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch("src.solidworks_mcp.agents.harness.Agent", MagicMock(return_value=mock_agent)):
            result = await run_validated_prompt(
                agent_file_name="test-agent.agent.md",
                model_name="github:openai/gpt-4.1",
                user_prompt="Test.",
                result_type=ManufacturabilityReview,
                max_retries_on_recoverable=1,
                db_path=db_path,
            )

        assert isinstance(result, RecoverableFailure)

    @pytest.mark.asyncio
    async def test_retries_on_recoverable_failure(
        self, agent_file: Path, db_path: Path, valid_review: ManufacturabilityReview, monkeypatch
    ):
        """First attempt returns RecoverableFailure; second succeeds."""
        monkeypatch.chdir(agent_file.parent.parent.parent)

        failure = RecoverableFailure(
            explanation="First attempt failed here.",
            remediation_steps=["Try narrower prompt"],
            retry_focus="Focus on geometry only.",
            should_retry=True,
        )

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(
            side_effect=[
                SimpleNamespace(data=failure),
                SimpleNamespace(data=valid_review),
            ]
        )

        with patch("src.solidworks_mcp.agents.harness.Agent", MagicMock(return_value=mock_agent)):
            result = await run_validated_prompt(
                agent_file_name="test-agent.agent.md",
                model_name="github:openai/gpt-4.1",
                user_prompt="Test.",
                result_type=ManufacturabilityReview,
                max_retries_on_recoverable=1,
                db_path=db_path,
            )

        assert isinstance(result, ManufacturabilityReview)
        assert mock_agent.run.call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_retries_returns_failure(
        self, agent_file: Path, db_path: Path, monkeypatch
    ):
        """Recoverable failures for all attempts → return last RecoverableFailure."""
        monkeypatch.chdir(agent_file.parent.parent.parent)

        failure = RecoverableFailure(
            explanation="Always fails in this test.",
            should_retry=True,
        )

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=SimpleNamespace(data=failure))

        with patch("src.solidworks_mcp.agents.harness.Agent", MagicMock(return_value=mock_agent)):
            result = await run_validated_prompt(
                agent_file_name="test-agent.agent.md",
                model_name="github:openai/gpt-4.1",
                user_prompt="Test.",
                result_type=ManufacturabilityReview,
                max_retries_on_recoverable=2,
                db_path=db_path,
            )

        assert isinstance(result, RecoverableFailure)
        # Initial attempt + 2 retries = 3 calls
        assert mock_agent.run.call_count == 3

    @pytest.mark.asyncio
    async def test_recoverable_failure_no_remediation_steps(
        self, agent_file: Path, db_path: Path, monkeypatch
    ):
        """Covers the empty remediation_steps branch in the retry build."""
        monkeypatch.chdir(agent_file.parent.parent.parent)

        failure = RecoverableFailure(
            explanation="Failure with no steps.",
            remediation_steps=[],  # empty list
            retry_focus=None,       # no retry focus
            should_retry=False,
        )

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=SimpleNamespace(data=failure))

        with patch("src.solidworks_mcp.agents.harness.Agent", MagicMock(return_value=mock_agent)):
            result = await run_validated_prompt(
                agent_file_name="test-agent.agent.md",
                model_name="github:openai/gpt-4.1",
                user_prompt="Test.",
                result_type=ManufacturabilityReview,
                db_path=db_path,
            )

        assert isinstance(result, RecoverableFailure)


# ---------------------------------------------------------------------------
# run_validated_prompt — exception path
# ---------------------------------------------------------------------------


class TestRunValidatedPromptException:
    @pytest.mark.asyncio
    async def test_raises_and_logs_error(
        self, agent_file: Path, db_path: Path, monkeypatch
    ):
        monkeypatch.chdir(agent_file.parent.parent.parent)

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("Model API unreachable"))

        with patch("src.solidworks_mcp.agents.harness.Agent", MagicMock(return_value=mock_agent)):
            with pytest.raises(RuntimeError, match="Model API unreachable"):
                await run_validated_prompt(
                    agent_file_name="test-agent.agent.md",
                    model_name="github:openai/gpt-4.1",
                    user_prompt="Test.",
                    result_type=ManufacturabilityReview,
                    db_path=db_path,
                )

        from sqlmodel import Session, create_engine, select
        from src.solidworks_mcp.agents.history_db import AgentRun, init_db

        init_db(db_path)
        engine = create_engine(f"sqlite:///{db_path}")
        with Session(engine) as session:
            runs = session.exec(select(AgentRun)).all()
        engine.dispose()

        assert any(r.status == "error" for r in runs)

    @pytest.mark.asyncio
    async def test_import_error_raises_runtime(self, agent_file: Path, monkeypatch):
        """When pydantic_ai is not importable, run_validated_prompt raises RuntimeError."""
        monkeypatch.chdir(agent_file.parent.parent.parent)

        import src.solidworks_mcp.agents.harness as harness_module

        original_agent = harness_module.Agent
        original_err = harness_module.IMPORT_ERROR

        try:
            harness_module.Agent = None
            harness_module.IMPORT_ERROR = ImportError("pydantic_ai not installed")
            with pytest.raises(RuntimeError, match="pydantic_ai is not importable"):
                await run_validated_prompt(
                    agent_file_name="test-agent.agent.md",
                    model_name="github:openai/gpt-4.1",
                    user_prompt="Test.",
                    result_type=ManufacturabilityReview,
                )
        finally:
            harness_module.Agent = original_agent
            harness_module.IMPORT_ERROR = original_err
