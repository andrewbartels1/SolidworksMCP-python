"""CLI for running validated prompt smoke tests against custom agent files."""

from __future__ import annotations

import asyncio
import os
from enum import StrEnum
from typing import Annotated

import typer

from .harness import pretty_json, run_validated_prompt
from .schemas import DocsPlan, ManufacturabilityReview, RecoverableFailure, ReconstructionPlan

app = typer.Typer(
    name="smoke-test",
    help="Run validated custom-agent prompt tests against the SolidWorks MCP agents.",
    no_args_is_help=True,
)


class SchemaChoice(StrEnum):
    manufacturability = "manufacturability"
    docs = "docs"
    reconstruction = "reconstruction"


def _resolve_model(
    anthropic: bool,
    claude_model: str,
    github_models: bool,
    github_model: str,
    model: str | None,
) -> str:
    """Resolve effective model id from CLI options."""
    if github_models:
        return f"github:{github_model}"

    if anthropic:
        return f"anthropic:{claude_model}"

    if not model:
        raise typer.BadParameter(
            "--model is required unless --github-models or --anthropic is enabled. "
            "Recommended: --github-models (requires GH_TOKEN with models:read scope).",
            param_hint="'--model'",
        )

    return model


def _ensure_provider_credentials(model: str) -> None:
    """Provide actionable credential guidance before model invocation."""
    if model.startswith("github:"):
        github_token = os.getenv("GITHUB_API_KEY") or os.getenv("GH_TOKEN")
        if not github_token:
            # Fall back to `gh auth token` if the gh CLI is available and authenticated.
            try:
                import subprocess
                result = subprocess.run(
                    ["gh", "auth", "token"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    github_token = result.stdout.strip()
            except Exception:
                pass
        if not github_token:
            raise typer.BadParameter(
                "GitHub Models requires GITHUB_API_KEY (or GH_TOKEN) with models:read scope.\n"
                "Options:\n"
                "  1. Run: gh auth login  (GitHub CLI — free with Copilot subscription)\n"
                "  2. Or set: $env:GH_TOKEN = 'github_pat_...'",
                param_hint="'--github-models'",
            )
        # pydantic-ai GitHubProvider looks for GITHUB_API_KEY.
        os.environ.setdefault("GITHUB_API_KEY", github_token)
        return

    if model.startswith("anthropic:") and not os.getenv("ANTHROPIC_API_KEY"):
        raise typer.BadParameter(
            "ANTHROPIC_API_KEY is not set.\n"
            "Export your key before running smoke_test:\n"
            "  $env:ANTHROPIC_API_KEY = 'sk-ant-...'\n"
            "Or use --github-models to run via GitHub Models with a GitHub PAT.",
            param_hint="'--anthropic'",
        )

    if model.startswith("openai:") and not os.getenv("OPENAI_API_KEY"):
        raise typer.BadParameter(
            "OPENAI_API_KEY is not set. Copilot subscription cannot be reused as an "
            "OpenAI API key for local pydantic-ai scripts. "
            "Use --github-models instead.",
            param_hint="'--model'",
        )


async def _run(
    agent_file: str,
    model_name: str,
    prompt: str,
    schema: SchemaChoice,
    max_retries_on_recoverable: int,
) -> int:
    if schema == SchemaChoice.manufacturability:
        schema_type = ManufacturabilityReview
    elif schema == SchemaChoice.reconstruction:
        schema_type = ReconstructionPlan
    else:
        schema_type = DocsPlan
    result = await run_validated_prompt(
        agent_file_name=agent_file,
        model_name=model_name,
        user_prompt=prompt,
        result_type=schema_type,
        max_retries_on_recoverable=max_retries_on_recoverable,
    )

    if isinstance(result, RecoverableFailure):
        typer.echo("RecoverableFailure returned after retry attempts:")
    typer.echo(pretty_json(result))
    return 0


@app.command()
def run(
    agent_file: Annotated[
        str,
        typer.Option("--agent-file", help="Agent filename in .github/agents/", show_default=False),
    ],
    prompt: Annotated[
        str,
        typer.Option("--prompt", help="User prompt to run", show_default=False),
    ],
    github_models: Annotated[
        bool,
        typer.Option(
            "--github-models",
            help="Use GitHub Models provider (recommended). Requires GH_TOKEN or GITHUB_API_KEY with models:read scope.",
        ),
    ] = False,
    github_model: Annotated[
        str,
        typer.Option("--github-model", help="GitHub Models catalog id, e.g. openai/gpt-4.1 or mistral-ai/mistral-large."),
    ] = "openai/gpt-4.1",
    anthropic: Annotated[
        bool,
        typer.Option(
            "--anthropic",
            help="Use Anthropic Claude (requires ANTHROPIC_API_KEY with active billing).",
        ),
    ] = False,
    claude_model: Annotated[
        str,
        typer.Option(
            "--claude-model",
            help="Anthropic model id, e.g. claude-sonnet-4-6 or claude-opus-4-6.",
        ),
    ] = "claude-sonnet-4-6",
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Explicit PydanticAI model spec, e.g. openai:gpt-4.1. Overridden by --anthropic/--github-models.",
        ),
    ] = None,
    schema: Annotated[
        SchemaChoice,
        typer.Option("--schema", help="Validation schema expected from the model output."),
    ] = SchemaChoice.manufacturability,
    max_retries_on_recoverable: Annotated[
        int,
        typer.Option(
            "--max-retries-on-recoverable",
            help="Automatic retry attempts when model returns RecoverableFailure.",
        ),
    ] = 1,
) -> None:
    """Run a validated custom-agent prompt test and print structured JSON output."""
    model_name = _resolve_model(anthropic, claude_model, github_models, github_model, model)
    _ensure_provider_credentials(model_name)
    raise SystemExit(asyncio.run(_run(agent_file, model_name, prompt, schema, max_retries_on_recoverable)))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
