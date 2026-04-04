"""PydanticAI harness for validating custom agent prompt responses."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from .history_db import ErrorRecord, insert_error, insert_run
from .schemas import RecoverableFailure

try:
    from pydantic_ai import Agent
except ImportError as exc:  # pragma: no cover
    Agent = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


TModel = TypeVar("TModel", bound=BaseModel)
AGENTS_DIR = Path(".github") / "agents"


def _load_agent_prompt(agent_file_name: str) -> str:
    path = AGENTS_DIR / agent_file_name
    raw = path.read_text(encoding="utf-8")

    # Strip YAML frontmatter and keep only instruction body.
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return raw.strip()


def _extract_data(result: Any) -> Any:
    if hasattr(result, "data"):
        return result.data
    if hasattr(result, "output"):
        return result.output
    return result


async def run_validated_prompt(
    *,
    agent_file_name: str,
    model_name: str,
    user_prompt: str,
    result_type: type[TModel],
    max_retries_on_recoverable: int = 1,
    db_path: Path | None = None,
) -> TModel | RecoverableFailure:
    """Run one prompt through PydanticAI and validate the output schema."""
    if Agent is None:  # pragma: no cover
        raise RuntimeError(
            "pydantic_ai is not importable. Install dependencies and retry."
        ) from IMPORT_ERROR

    base_run_id = str(uuid.uuid4())
    instructions = _load_agent_prompt(agent_file_name)
    system_prompt = (
        f"{instructions}\n\n"
        "If you cannot safely produce the requested structured output, return "
        "a RecoverableFailure with concrete remediation steps and a focused retry hint."
    )

    attempt = 0
    current_prompt = user_prompt

    while True:
        attempt += 1
        run_id = f"{base_run_id}-a{attempt}"

        prompt_snapshot = current_prompt

        agent = Agent(
            model_name,
            system_prompt=system_prompt,
            output_type=[result_type, RecoverableFailure],
        )

        try:
            result = await agent.run(current_prompt)
            payload = _extract_data(result)

            if isinstance(payload, RecoverableFailure):
                insert_run(
                    run_id=run_id,
                    agent_name=agent_file_name,
                    prompt=prompt_snapshot,
                    status="recoverable_failure",
                    output_json=payload.model_dump_json(indent=2),
                    model_name=model_name,
                    db_path=db_path,
                )
                insert_error(
                    ErrorRecord(
                        source="pydantic_ai",
                        tool_name="run_validated_prompt",
                        error_type="RecoverableFailure",
                        error_message=payload.explanation,
                        root_cause=payload.explanation,
                        remediation="; ".join(payload.remediation_steps)
                        if payload.remediation_steps
                        else "Follow retry_focus guidance and retry with narrower scope.",
                    ),
                    run_id=run_id,
                    db_path=db_path,
                )
                if payload.should_retry and attempt <= max_retries_on_recoverable:
                    retry_hint = (
                        payload.retry_focus or "Narrow scope and clarify assumptions."
                    )
                    remediation = "\n".join(
                        f"- {step}" for step in payload.remediation_steps
                    )
                    current_prompt = (
                        f"{user_prompt}\n\n"
                        "Retry context from previous recoverable failure:\n"
                        f"Explanation: {payload.explanation}\n"
                        f"Retry focus: {retry_hint}\n"
                        f"Remediation steps:\n{remediation}"
                    )
                    continue
                return payload

            validated = (
                payload
                if isinstance(payload, result_type)
                else result_type.model_validate(payload)
            )

            insert_run(
                run_id=run_id,
                agent_name=agent_file_name,
                prompt=prompt_snapshot,
                status="success",
                output_json=validated.model_dump_json(indent=2),
                model_name=model_name,
                db_path=db_path,
            )
            return validated
        except Exception as exc:
            insert_run(
                run_id=run_id,
                agent_name=agent_file_name,
                prompt=current_prompt,
                status="error",
                output_json=None,
                model_name=model_name,
                db_path=db_path,
            )
            insert_error(
                ErrorRecord(
                    source="pydantic_ai",
                    tool_name="run_validated_prompt",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    root_cause="Agent output failed schema validation or model invocation",
                    remediation=(
                        "Review response schema, verify model provider credentials, and re-run with a narrower prompt."
                    ),
                ),
                run_id=run_id,
                db_path=db_path,
            )
            raise


def pretty_json(model: BaseModel) -> str:
    """Return pretty JSON for test output snapshots."""
    return json.dumps(model.model_dump(mode="json"), indent=2)
