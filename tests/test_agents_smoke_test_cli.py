"""Tests for src/solidworks_mcp/agents/smoke_test.py CLI — targeting 100% coverage.

All tests here are unit tests that mock the LLM call. No live API calls are made.
Live LLM smoke tests are in tests/test_smoke_agents_live.py (marked `smoke`).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.solidworks_mcp.agents.smoke_test import (
    SchemaChoice,
    _ensure_provider_credentials,
    _resolve_model,
    app,
)
import src.solidworks_mcp.agents.smoke_test as smoke_module


runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text (so assertions are CI-safe)."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


# ---------------------------------------------------------------------------
# _resolve_model
# ---------------------------------------------------------------------------


class TestResolveModel:
    def test_github_models_prefix(self):
        model = _resolve_model(
            anthropic=False,
            claude_model="claude-sonnet-4-6",
            github_models=True,
            github_model="openai/gpt-4.1",
            model=None,
        )
        assert model == "github:openai/gpt-4.1"

    def test_github_models_custom_model(self):
        model = _resolve_model(
            anthropic=False,
            claude_model="claude-sonnet-4-6",
            github_models=True,
            github_model="mistral-ai/mistral-large",
            model=None,
        )
        assert model == "github:mistral-ai/mistral-large"

    def test_anthropic_prefix(self):
        model = _resolve_model(
            anthropic=True,
            claude_model="claude-sonnet-4-6",
            github_models=False,
            github_model="openai/gpt-4.1",
            model=None,
        )
        assert model == "anthropic:claude-sonnet-4-6"

    def test_anthropic_custom_model(self):
        model = _resolve_model(
            anthropic=True,
            claude_model="claude-opus-4-6",
            github_models=False,
            github_model="openai/gpt-4.1",
            model=None,
        )
        assert model == "anthropic:claude-opus-4-6"

    def test_explicit_model_string(self):
        model = _resolve_model(
            anthropic=False,
            claude_model="claude-sonnet-4-6",
            github_models=False,
            github_model="openai/gpt-4.1",
            model="openai:gpt-4.1",
        )
        assert model == "openai:gpt-4.1"

    def test_github_models_takes_precedence_over_anthropic(self):
        """--github-models is evaluated first in _resolve_model."""
        model = _resolve_model(
            anthropic=True,
            claude_model="claude-sonnet-4-6",
            github_models=True,
            github_model="openai/gpt-4.1",
            model=None,
        )
        assert model.startswith("github:")

    def test_raises_when_no_provider(self):
        import typer

        with pytest.raises(typer.BadParameter):
            _resolve_model(
                anthropic=False,
                claude_model="claude-sonnet-4-6",
                github_models=False,
                github_model="openai/gpt-4.1",
                model=None,
            )


# ---------------------------------------------------------------------------
# _ensure_provider_credentials
# ---------------------------------------------------------------------------


class TestEnsureProviderCredentials:
    def test_github_with_env_var(self, monkeypatch):
        monkeypatch.delenv("GITHUB_API_KEY", raising=False)
        monkeypatch.setenv("GH_TOKEN", "gho_test_token")
        _ensure_provider_credentials("github:openai/gpt-4.1")
        assert os.environ.get("GITHUB_API_KEY") == "gho_test_token"

    def test_github_with_github_api_key(self, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_API_KEY", "ghp_test_key")
        _ensure_provider_credentials("github:openai/gpt-4.1")
        assert os.environ["GITHUB_API_KEY"] == "ghp_test_key"

    def test_github_fallback_to_gh_cli(self, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_API_KEY", raising=False)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="gh_cli_token\n")
            _ensure_provider_credentials("github:openai/gpt-4.1")

        assert os.environ.get("GITHUB_API_KEY") == "gh_cli_token"

    def test_github_fallback_gh_cli_fails(self, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_API_KEY", raising=False)
        # Clear any previously set key from earlier tests
        monkeypatch.delenv("GITHUB_API_KEY", raising=False)

        import typer

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            with pytest.raises(typer.BadParameter, match="models:read"):
                _ensure_provider_credentials("github:openai/gpt-4.1")

    def test_github_fallback_gh_cli_exception(self, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_API_KEY", raising=False)

        import typer

        with patch("subprocess.run", side_effect=FileNotFoundError("gh not found")):
            with pytest.raises(typer.BadParameter):
                _ensure_provider_credentials("github:openai/gpt-4.1")

    def test_anthropic_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        import typer

        with pytest.raises(typer.BadParameter, match="ANTHROPIC_API_KEY"):
            _ensure_provider_credentials("anthropic:claude-sonnet-4-6")

    def test_anthropic_with_key_set_passes(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        _ensure_provider_credentials("anthropic:claude-sonnet-4-6")  # should not raise

    def test_openai_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        import typer

        with pytest.raises(typer.BadParameter, match="OPENAI_API_KEY"):
            _ensure_provider_credentials("openai:gpt-4.1")

    def test_openai_with_key_set_passes(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        _ensure_provider_credentials("openai:gpt-4.1")  # should not raise

    def test_unknown_provider_passes_silently(self):
        """Unrecognized model prefixes don't raise — not our responsibility."""
        _ensure_provider_credentials("someother:model")


# ---------------------------------------------------------------------------
# SchemaChoice enum
# ---------------------------------------------------------------------------


class TestSchemaChoice:
    def test_manufacturability_value(self):
        assert SchemaChoice.manufacturability == "manufacturability"

    def test_docs_value(self):
        assert SchemaChoice.docs == "docs"

    def test_is_str(self):
        assert isinstance(SchemaChoice.manufacturability, str)


# ---------------------------------------------------------------------------
# CLI integration via typer.testing.CliRunner
# ---------------------------------------------------------------------------


class TestCLIApp:
    def _make_agent_dir(self, tmp_path: Path) -> Path:
        agents_dir = tmp_path / ".github" / "agents"
        agents_dir.mkdir(parents=True)
        agent_file = agents_dir / "test-agent.agent.md"
        agent_file.write_text(
            "---\nname: Test\n---\nYou are a test agent.\n", encoding="utf-8"
        )
        return tmp_path

    def test_help_output(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "agent-file" in _strip_ansi(result.output)

    def test_missing_required_args(self):
        result = runner.invoke(app, [])
        # No args → shows help (no_args_is_help=True); exit code is 0 or 2 depending on Typer version
        assert result.exit_code in (0, 2)

    def test_run_manufacturability_success(self, tmp_path: Path, monkeypatch):
        cwd = self._make_agent_dir(tmp_path)
        monkeypatch.chdir(cwd)
        monkeypatch.setenv("GH_TOKEN", "test_token")

        from src.solidworks_mcp.agents.schemas import ManufacturabilityReview

        review = ManufacturabilityReview(
            summary="CLI test summary here.",
            orientation_guidance="Flat on bed.",
            build_volume_check="Fits envelope.",
        )

        with patch(
            "src.solidworks_mcp.agents.smoke_test.run_validated_prompt",
            new=AsyncMock(return_value=review),
        ):
            result = runner.invoke(
                app,
                [
                    "--agent-file",
                    "test-agent.agent.md",
                    "--github-models",
                    "--schema",
                    "manufacturability",
                    "--prompt",
                    "Design a snap-fit cover.",
                ],
            )

        assert result.exit_code == 0
        assert "summary" in result.output

    def test_run_docs_schema(self, tmp_path: Path, monkeypatch):
        cwd = self._make_agent_dir(tmp_path)
        monkeypatch.chdir(cwd)
        monkeypatch.setenv("GH_TOKEN", "test_token")

        from src.solidworks_mcp.agents.schemas import DocsPlan

        plan = DocsPlan(
            audience="CAD engineers",
            objective="Document bracket workflow.",
        )

        with patch(
            "src.solidworks_mcp.agents.smoke_test.run_validated_prompt",
            new=AsyncMock(return_value=plan),
        ):
            result = runner.invoke(
                app,
                [
                    "--agent-file",
                    "test-agent.agent.md",
                    "--github-models",
                    "--schema",
                    "docs",
                    "--prompt",
                    "Plan a tutorial.",
                ],
            )

        assert result.exit_code == 0
        assert "audience" in result.output

    def test_run_prints_recoverable_failure_label(self, tmp_path: Path, monkeypatch):
        cwd = self._make_agent_dir(tmp_path)
        monkeypatch.chdir(cwd)
        monkeypatch.setenv("GH_TOKEN", "test_token")

        failure = RecoverableFailure(
            explanation="Could not produce schema output.",
            should_retry=False,
        )

        with patch(
            "src.solidworks_mcp.agents.smoke_test.run_validated_prompt",
            new=AsyncMock(return_value=failure),
        ):
            result = runner.invoke(
                app,
                [
                    "--agent-file",
                    "test-agent.agent.md",
                    "--github-models",
                    "--schema",
                    "manufacturability",
                    "--prompt",
                    "Prompt that fails.",
                ],
            )

        assert "RecoverableFailure" in result.output

    def test_anthropic_flag_routes_correctly(self, tmp_path: Path, monkeypatch):
        cwd = self._make_agent_dir(tmp_path)
        monkeypatch.chdir(cwd)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        from src.solidworks_mcp.agents.schemas import ManufacturabilityReview

        review = ManufacturabilityReview(
            summary="Anthropic CLI test summary.",
            orientation_guidance="Flat on bed.",
            build_volume_check="Fits envelope.",
        )

        captured_model = []

        async def _mock_run(**kwargs):
            captured_model.append(kwargs.get("model_name"))
            return review

        with patch(
            "src.solidworks_mcp.agents.smoke_test.run_validated_prompt", new=_mock_run
        ):
            result = runner.invoke(
                app,
                [
                    "--agent-file",
                    "test-agent.agent.md",
                    "--anthropic",
                    "--claude-model",
                    "claude-sonnet-4-6",
                    "--schema",
                    "manufacturability",
                    "--prompt",
                    "Test.",
                ],
            )

        assert result.exit_code == 0
        assert captured_model[0] == "anthropic:claude-sonnet-4-6"

    def test_max_retries_passed_through(self, tmp_path: Path, monkeypatch):
        cwd = self._make_agent_dir(tmp_path)
        monkeypatch.chdir(cwd)
        monkeypatch.setenv("GH_TOKEN", "test_token")

        from src.solidworks_mcp.agents.schemas import ManufacturabilityReview

        review = ManufacturabilityReview(
            summary="Retries test summary here.",
            orientation_guidance="Flat on bed.",
            build_volume_check="Fits envelope.",
        )

        captured_retries = []

        async def _mock_run(**kwargs):
            captured_retries.append(kwargs.get("max_retries_on_recoverable"))
            return review

        with patch(
            "src.solidworks_mcp.agents.smoke_test.run_validated_prompt", new=_mock_run
        ):
            result = runner.invoke(
                app,
                [
                    "--agent-file",
                    "test-agent.agent.md",
                    "--github-models",
                    "--schema",
                    "manufacturability",
                    "--max-retries-on-recoverable",
                    "3",
                    "--prompt",
                    "Test.",
                ],
            )

        assert result.exit_code == 0
        assert captured_retries[0] == 3


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


class TestMainEntryPoint:
    def test_main_is_callable(self):
        from src.solidworks_mcp.agents.smoke_test import main

        assert callable(main)


# ---------------------------------------------------------------------------
# Import at module top avoids repetitive imports in tests
# ---------------------------------------------------------------------------

from src.solidworks_mcp.agents.schemas import RecoverableFailure  # noqa: E402
