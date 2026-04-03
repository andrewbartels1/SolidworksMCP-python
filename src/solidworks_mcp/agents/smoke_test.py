"""CLI for running validated prompt smoke tests against custom agent files."""

from __future__ import annotations

import argparse
import asyncio
import os

from .harness import pretty_json, run_validated_prompt
from .schemas import DocsPlan, ManufacturabilityReview, RecoverableFailure


def _resolve_model(args: argparse.Namespace) -> str:
    """Resolve effective model id from CLI options."""
    if args.github_models:
        github_model = args.github_model or "openai/gpt-4.1"
        return f"github:{github_model}"

    if not args.model:
        raise RuntimeError("--model is required unless --github-models is enabled.")

    return args.model


def _ensure_provider_credentials(model: str) -> None:
    """Provide actionable credential guidance before model invocation."""
    if model.startswith("github:"):
        github_token = os.getenv("GITHUB_API_KEY") or os.getenv("GH_TOKEN")
        if not github_token:
            raise RuntimeError(
                "GitHub Models requires GITHUB_API_KEY (or GH_TOKEN) with models:read scope. "
                "Create a GitHub PAT and export it before running smoke_test."
            )

        # pydantic-ai GitHubProvider looks for GITHUB_API_KEY.
        os.environ.setdefault("GITHUB_API_KEY", github_token)
        return

    if model.startswith("openai:") and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copilot chat subscription cannot be reused as an OpenAI API key for local pydantic-ai scripts. "
            "Use a provider API key, or use --github-models to run through GitHub Models with a GitHub token."
        )

    if model.startswith("anthropic:") and not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copilot chat subscription cannot be reused as an Anthropic API key for local pydantic-ai scripts."
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a validated custom-agent prompt test"
    )
    parser.add_argument(
        "--agent-file", required=True, help="Agent filename in .github/agents"
    )
    parser.add_argument("--model", help="PydanticAI model spec, e.g. openai:gpt-4.1")
    parser.add_argument(
        "--github-models",
        action="store_true",
        help="Use GitHub Models provider (maps to model id github:<provider/model>).",
    )
    parser.add_argument(
        "--github-model",
        default="openai/gpt-4.1",
        help="GitHub Models catalog id, e.g. openai/gpt-4.1 or mistral-ai/mistral-large.",
    )
    parser.add_argument("--prompt", required=True, help="User prompt to run")
    parser.add_argument(
        "--schema",
        choices=["manufacturability", "docs"],
        default="manufacturability",
        help="Validation schema expected from the model output",
    )
    parser.add_argument(
        "--max-retries-on-recoverable",
        type=int,
        default=1,
        help="Automatic retry attempts when model returns RecoverableFailure.",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    model_name = _resolve_model(args)
    _ensure_provider_credentials(model_name)

    schema_type = (
        ManufacturabilityReview if args.schema == "manufacturability" else DocsPlan
    )
    result = await run_validated_prompt(
        agent_file_name=args.agent_file,
        model_name=model_name,
        user_prompt=args.prompt,
        result_type=schema_type,
        max_retries_on_recoverable=args.max_retries_on_recoverable,
    )

    if isinstance(result, RecoverableFailure):
        print("RecoverableFailure returned after retry attempts:")
    print(pretty_json(result))
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
