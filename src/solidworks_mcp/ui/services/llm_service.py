"""LLM orchestration service for the Prefab CAD assistant dashboard.

Wraps all pydantic-ai calls for clarification, family inspection, and Go orchestration.
This module is the only place that imports pydantic-ai or subprocess for token retrieval.

Security note:
    ``_ensure_provider_credentials`` uses ``subprocess.run(["gh", "auth", "token"])``.
    # TODO: security review — subprocess token extraction.  Consider replacing with a
    # credential-store or environment-variable-only approach.
"""

from __future__ import annotations

import inspect as _inspect
import json
import os
import re
import subprocess  # noqa: S404  # TODO: security review — subprocess token extraction
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from ...agents.history_db import (
    get_design_session,
    insert_evidence_link,
    insert_tool_call_record,
    replace_plan_checkpoints,
    upsert_design_session,
)
from ._utils import (
    DEFAULT_API_ORIGIN,
    DEFAULT_SESSION_ID,
    DEFAULT_SOURCE_MODE,
    DEFAULT_USER_GOAL,
    normalize_model_name_for_provider,
    persist_ui_action,
    merge_metadata,
    sanitize_ui_text,
)

# ---------------------------------------------------------------------------
# Optional pydantic-ai imports — library is an optional dependency.
# ---------------------------------------------------------------------------
try:
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    try:
        from pydantic_ai.mcp import MCPServerStreamableHTTP
    except ImportError:
        MCPServerStreamableHTTP = None  # type: ignore[assignment]

    try:
        from pydantic_ai import RecoverableFailure
    except ImportError:
        # Older pydantic-ai builds expose it at a different path.
        try:
            from pydantic_ai.result import RecoverableFailure  # type: ignore[no-redef]
        except ImportError:
            # Newer pydantic-ai builds may not expose RecoverableFailure.
            # Keep Agent support enabled and use a local schema fallback.
            class RecoverableFailure(BaseModel):  # type: ignore[no-redef]
                """Fallback recoverable-failure schema for pydantic-ai compatibility."""

                explanation: str = ""
                remediation_steps: list[str] = Field(default_factory=list)
                retry_focus: str = ""
                should_retry: bool = False
except ImportError:
    Agent = None  # type: ignore[assignment]
    OpenAIChatModel = None  # type: ignore[assignment]
    OpenAIProvider = None  # type: ignore[assignment]
    MCPServerStreamableHTTP = None  # type: ignore[assignment]

    class RecoverableFailure(BaseModel):  # type: ignore[no-redef]
        """Fallback stub used when pydantic-ai is not installed."""

        explanation: str = ""
        remediation_steps: list[str] = Field(default_factory=list)
        retry_focus: str = ""
        should_retry: bool = False


# ---------------------------------------------------------------------------
# LLM response schemas (moved from service.py to avoid duplicate definitions)
# ---------------------------------------------------------------------------


class ClarificationResponse(BaseModel):
    """LLM response for goal clarification.

    Attributes:
        normalized_brief: Concise manufacturing-ready description of the design goal.
        questions: Follow-up questions that unblock the next modelling step.
    """

    normalized_brief: str = Field(min_length=10)
    questions: list[str] = Field(default_factory=list)


class CheckpointCandidate(BaseModel):
    """One suggested execution checkpoint.

    Attributes:
        title: Short human-readable label.
        allowed_tools: MCP tool names allowed at this checkpoint.
        rationale: Reasoning for including this step.
        execution: Optional structured execution hints used by checkpoint runner.
    """

    title: str = Field(min_length=3)
    allowed_tools: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=5)
    execution: dict[str, Any] = Field(default_factory=dict)


class FamilyInspection(BaseModel):
    """LLM response for feature-family classification.

    Attributes:
        family: Detected SolidWorks feature family name.
        confidence: Model confidence level.
        evidence: Supporting evidence lines.
        warnings: Contradictory or low-confidence warnings.
        checkpoints: Suggested checkpoint plan for human review.
    """

    family: str = Field(min_length=3)
    confidence: Literal["low", "medium", "high"]
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checkpoints: list[CheckpointCandidate] = Field(default_factory=list)


def _extract_explicit_feature_order(user_goal: str) -> list[str]:
    """Extract feature order tokens from goals that include an explicit ``A -> B -> C`` sequence."""
    if "->" not in (user_goal or ""):
        return []

    pattern = r"([A-Za-z][A-Za-z0-9_-]*(?:\s*->\s*[A-Za-z][A-Za-z0-9_-]*){1,9})"
    match = re.search(pattern, user_goal)
    if not match:
        return []

    sequence = match.group(1)
    ordered = [part.strip() for part in sequence.split("->") if part.strip()]
    return ordered


def _extract_blind_depth_mm(user_goal: str) -> float | None:
    """Extract blind-depth numeric value from phrases like ``blind 10.0 mm``."""
    match = re.search(r"blind\s+([0-9]+(?:\.[0-9]+)?)\s*mm", user_goal, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _tools_for_feature_name(feature_name: str, position: int) -> list[str]:
    """Map a feature token to an executable tool subset used by checkpoint execution."""
    lower = feature_name.strip().lower()
    if "sketch" in lower:
        # First sketch should establish profile edges; later sketches usually add detail geometry.
        return (
            ["create_sketch", "add_line", "exit_sketch"]
            if position == 1
            else ["create_sketch", "add_circle", "exit_sketch"]
        )
    if "cut" in lower:
        return ["create_cut"]
    if "revolve" in lower:
        return ["create_revolve"]
    if "extrude" in lower:
        return ["create_extrusion"]
    return ["analyze_geometry"]


def _family_for_feature_order(ordered_features: list[str], current_family: str) -> str:
    """Infer family from explicit feature sequence, preferring deterministic extrusion flows."""
    lowered = [item.strip().lower() for item in ordered_features]
    if any("assembly" in item for item in lowered):
        return "assembly"
    if any("revolve" in item for item in lowered):
        return "revolve"
    if any(token in item for item in lowered for token in ("extrude", "cut", "sketch")):
        return "extrude"
    return current_family


def _coerce_explicit_feature_order_plan(
    user_goal: str,
    result: FamilyInspection,
) -> FamilyInspection:
    """Coerce checkpoints to an explicit feature sequence when the goal provides one."""
    ordered_features = _extract_explicit_feature_order(user_goal)
    if len(ordered_features) < 2:
        return result

    blind_depth_mm = _extract_blind_depth_mm(user_goal)
    checkpoints: list[CheckpointCandidate] = []
    for index, name in enumerate(ordered_features, start=1):
        lower = name.strip().lower()
        execution: dict[str, Any] = {
            "feature_name": name,
            "step_index": index,
            "goal": f"Create {name}",
        }

        if "sketch" in lower and index == 1:
            execution.update(
                {
                    "sketch_plane": "Top",
                    "profile": "closed_rect",
                    "rect_width_mm": 40.0,
                    "rect_height_mm": 24.0,
                }
            )
        elif "sketch" in lower:
            execution.update(
                {
                    "sketch_name": name,
                    "sketch_plane": "Top",
                    "profile": "circle",
                    "circle_center_mm": [20.0, 12.0],
                    "circle_radius_mm": 4.0,
                }
            )

        if "extrude" in lower:
            execution.update(
                {
                    "depth_mm": 10.0,
                    "prepare_profile": "closed_rect",
                    "sketch_plane": "Top",
                    "rect_width_mm": 40.0,
                    "rect_height_mm": 24.0,
                }
            )
        if "cut" in lower and blind_depth_mm is not None:
            prior_sketch = next(
                (
                    feature
                    for feature in reversed(ordered_features[: index - 1])
                    if "sketch" in feature.lower()
                ),
                "Sketch1",
            )
            execution.update(
                {
                    "depth_mm": blind_depth_mm,
                    "sketch_name": prior_sketch,
                    "prepare_base_extrusion": True,
                    "prepare_profile": "circle",
                    "sketch_plane": "Top",
                    "circle_center_mm": [20.0, 12.0],
                    "circle_radius_mm": 4.0,
                    "base_depth_mm": 10.0,
                }
            )

        checkpoints.append(
            CheckpointCandidate(
                title=f"Create {name}",
                allowed_tools=_tools_for_feature_name(name, index),
                rationale=(
                    f"Follow the explicit feature order from the design goal: step {index} is {name}."
                ),
                execution=execution,
            )
        )

    return result.model_copy(
        update={
            "family": _family_for_feature_order(ordered_features, result.family),
            "confidence": "high" if len(ordered_features) >= 3 else result.confidence,
            "checkpoints": checkpoints,
            "warnings": [
                *result.warnings,
                "Checkpoint plan constrained to the explicit feature-order sequence in the design goal.",
            ],
        }
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_model_name(explicit_model: str | None = None) -> str:
    """Return the resolved model name, falling back to the environment variable.

    Args:
        explicit_model: Caller-supplied model string (may be ``None``).

    Returns:
        Model name string to pass to pydantic-ai.
    """
    return explicit_model or os.getenv("SOLIDWORKS_UI_MODEL", "github:openai/gpt-4.1")


def _ensure_provider_credentials(
    model_name: str,
    local_endpoint: str | None = None,
) -> None:
    """Verify that the required provider credential is present, raising otherwise.

    Args:
        model_name: Provider-qualified model name (e.g. ``"github:openai/gpt-4.1"``).
        local_endpoint: Optional base URL for a local LLM server.

    Raises:
        RuntimeError: When the required credential is missing.
    """
    # TODO: security review — subprocess token extraction.  Replace with env-only lookup.
    if model_name.startswith("github:"):
        github_token = os.getenv("GITHUB_API_KEY") or os.getenv("GH_TOKEN")
        if not github_token:
            try:
                result = subprocess.run(  # noqa: S603
                    ["gh", "auth", "token"],  # noqa: S607
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except Exception:
                result = None  # type: ignore[assignment]
            if result and result.returncode == 0:
                github_token = result.stdout.strip()
        if not github_token:
            raise RuntimeError(
                "Set GH_TOKEN or GITHUB_API_KEY with models:read scope before using the dashboard LLM actions."
            )
        os.environ.setdefault("GITHUB_API_KEY", github_token)
        return

    if model_name.startswith("openai:") and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY before using OpenAI model routing.")

    if model_name.startswith("anthropic:") and not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "Set ANTHROPIC_API_KEY before using Anthropic model routing."
        )

    if model_name.startswith("local:"):
        # Endpoint defaults to http://127.0.0.1:11434/v1 inside _build_agent_model;
        # no credential is needed for a local Ollama server.
        pass


def _build_agent_model(model_name: str, local_endpoint: str | None = None) -> Any:
    """Construct and return the pydantic-ai model object for the given name.

    Args:
        model_name: Provider-qualified model name.
        local_endpoint: Base URL used when ``model_name`` starts with ``"local:"``.

    Returns:
        Either an ``OpenAIChatModel`` instance or the bare string model name.

    Raises:
        RuntimeError: When the local-model path is requested but pydantic-ai's OpenAI
            provider is not installed.
    """
    if model_name.startswith("local:"):
        if OpenAIChatModel is None or OpenAIProvider is None:
            raise RuntimeError("pydantic-ai OpenAI provider support is not installed.")
        resolved_endpoint = local_endpoint or os.getenv(
            "SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"
        )
        provider = OpenAIProvider(
            base_url=resolved_endpoint,
            api_key=os.getenv("LOCAL_OPENAI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or "local",
        )
        return OpenAIChatModel(model_name.split(":", 1)[1], provider=provider)

    if model_name.startswith("github:"):
        if OpenAIChatModel is None:
            raise RuntimeError("pydantic-ai OpenAI support is not installed.")
        try:
            from pydantic_ai.providers.github import GitHubProvider  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "pydantic-ai GitHubProvider is not available in this environment."
            ) from exc
        gh_token = os.getenv("GITHUB_API_KEY") or os.getenv("GH_TOKEN")
        provider = GitHubProvider(**({} if gh_token is None else {"api_key": gh_token}))
        raw_model = model_name.split(":", 1)[1]  # e.g. "openai/gpt-4.1"
        return OpenAIChatModel(raw_model, provider=provider)

    return model_name


async def _run_structured_agent(
    *,
    system_prompt: str,
    user_prompt: str,
    result_type: type[BaseModel],
    model_name: str | None = None,
    local_endpoint: str | None = None,
) -> BaseModel | RecoverableFailure:
    """Run a pydantic-ai agent and return a structured result or a RecoverableFailure.

    Args:
        system_prompt: System-level instructions for the agent.
        user_prompt: User turn containing the planning request.
        result_type: Pydantic model class expected as the structured output.
        model_name: Optional provider-qualified model override.
        local_endpoint: Optional base URL for local LLM servers.

    Returns:
        Either an instance of ``result_type`` or a ``RecoverableFailure`` describing
        why the agent call failed and how to recover.
    """
    if Agent is None:  # pragma: no cover
        return RecoverableFailure(
            explanation="pydantic_ai is not installed in this environment.",
            remediation_steps=["Install project dependencies and retry."],
            retry_focus="Install pydantic-ai and a supported provider.",
            should_retry=False,
        )

    resolved_model = _resolve_model_name(model_name)
    resolved_endpoint = local_endpoint or os.getenv(
        "SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"
    )

    mcp_tool_catalog = (
        "## SOLIDWORKS MCP TOOL CATALOG\n"
        "Use these tool names in checkpoint plans and rationale fields:\n"
        "  open_model, get_model_info, list_features(include_suppressed), get_mass_properties,\n"
        "  classify_feature_tree, create_sketch, add_line, add_arc, add_circle, add_rectangle,\n"
        "  create_extrusion, create_revolve, create_cut, export_image, export_step, export_stl,\n"
        "  select_feature, check_interference [mocked until wired], analyze_geometry,\n"
        "  generate_vba_code, execute_macro\n"
        "Prefer tools in the order listed above (inspect → classify → plan → execute → verify).\n"
        "Do not invent tools not in this list."
    )
    enriched_system_prompt = (
        "## ROLE AND ORCHESTRATION AGENTS\n"
        f"{system_prompt}\n\n"
        "## AVAILABLE ORCHESTRATION AGENTS\n"
        "  - Feature-Tree Reconstruction agent: inspect → classify → delegate; safe checkpoint plans.\n"
        "  - Printer-Profile Tolerancing agent: converts printer/material inputs to explicit tolerance "
        "ranges per feature type (press-fit, sliding, snap, hinge, clip).\n"
        "  - SolidWorks Research Validator: validates material, clearance, and build-volume facts.\n\n"
        "## GUARDRAILS\n"
        "  - Use the SolidWorks MCP tool surface for actionable plans.\n"
        "  - Do not invent unavailable tools; prefer known MCP tool names.\n"
        "  - If confidence is low or the model is unavailable, propose inspection steps first.\n"
        "  - For sheet metal or advanced solid families, route to VBA-aware planning.\n"
        "  - Always include explicit tolerance/clearance values when manufacturing context is present."
    )
    enriched_user_prompt = f"## PLANNING REQUEST\n{user_prompt}\n\n{mcp_tool_catalog}"

    mcp_server_url = os.getenv("SOLIDWORKS_MCP_URL", "http://127.0.0.1:8000/")
    mcp_agent_tools = os.getenv("SOLIDWORKS_MCP_AGENT_TOOLS", "auto").lower()
    toolsets: list[Any] = []
    if mcp_agent_tools != "off" and MCPServerStreamableHTTP is not None:
        mcp_kwargs: dict[str, Any] = {"tool_prefix": "sw"}
        try:
            params = _inspect.signature(MCPServerStreamableHTTP).parameters
            if "include_instructions" in params:
                mcp_kwargs["include_instructions"] = True
        except (TypeError, ValueError):
            pass
        toolsets = [MCPServerStreamableHTTP(mcp_server_url, **mcp_kwargs)]

    _ensure_provider_credentials(resolved_model, resolved_endpoint)
    try:
        configured_model = _build_agent_model(resolved_model, resolved_endpoint)
        agent = Agent(
            configured_model,
            system_prompt=enriched_system_prompt,
            output_type=[result_type, RecoverableFailure],
            toolsets=toolsets if toolsets else None,
        )
        if toolsets:
            try:
                async with agent:
                    result = await agent.run(enriched_user_prompt)
            except Exception:
                logger.debug(
                    "MCP server at %s unreachable; falling back to planning-only agent run.",
                    mcp_server_url,
                )
                agent_fallback = Agent(
                    configured_model,
                    system_prompt=enriched_system_prompt,
                    output_type=[result_type, RecoverableFailure],
                )
                result = await agent_fallback.run(enriched_user_prompt)
        else:
            result = await agent.run(enriched_user_prompt)
    except Exception as exc:
        return RecoverableFailure(
            explanation=f"Model routing failed: {exc}",
            remediation_steps=[
                "Open Model Controls and run Auto-Detect Local Model, or switch provider/model to a supported value.",
            ],
            retry_focus="Use a provider-qualified model name, then retry this action.",
            should_retry=True,
        )
    payload = result.data if hasattr(result, "data") else result.output
    if isinstance(payload, RecoverableFailure):
        return payload
    return (
        payload
        if isinstance(payload, result_type)
        else result_type.model_validate(payload)
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def request_clarifications(
    session_id: str,
    user_goal: str,
    *,
    user_answer: str = "",
    db_path: Path | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Generate focused follow-up questions for the current design goal using LLM.

    Args:
        session_id: Dashboard session identifier.
        user_goal: Free-text description of the design intent.
        user_answer: Any previous answers the user has already provided.
        db_path: Optional SQLite path override.
        model_name: Optional provider-qualified model override.

    Returns:
        Full dashboard state payload.
    """
    from .session_service import build_dashboard_state, ensure_dashboard_session  # noqa: PLC0415

    ensure_dashboard_session(session_id, user_goal=user_goal, db_path=db_path)
    session_row = get_design_session(session_id, db_path=db_path) or {}
    meta = _parse_json_blob(session_row.get("metadata_json"))
    resolved_model = normalize_model_name_for_provider(
        model_name or meta.get("model_name"),
        provider=sanitize_ui_text(meta.get("model_provider"), "github"),
        profile=sanitize_ui_text(meta.get("model_profile"), "balanced"),
    )
    resolved_endpoint = sanitize_ui_text(
        meta.get("local_endpoint"),
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )

    answer_section = (
        f"\n## USER ANSWERS / CLARIFICATIONS\n{user_answer}" if user_answer else ""
    )
    assumptions_text = sanitize_ui_text(
        meta.get("assumptions_text"), "<none specified>"
    )
    prompt = (
        "## TASK\n"
        "Prepare a SolidWorks design brief using the Printer-Profile-Tolerancing skill.\n"
        "Return a normalized_brief and at most three clarifying_questions that unblock the next modeling step.\n\n"
        "## DESIGN GOAL\n"
        f"{user_goal}\n\n"
        "## MANUFACTURING ASSUMPTIONS\n"
        f"{assumptions_text}\n\n"
        "## MODEL CONTEXT\n"
        f"Active model path : {meta.get('active_model_path', '') or '<none>'}\n"
        f"Feature target refs: {meta.get('feature_target_text', '') or '<none>'}\n"
        f"Reference corpus   : {meta.get('rag_provenance_text', '') or '<none>'}"
        f"{answer_section}\n\n"
        "## OUTPUT CONTRACT\n"
        "normalized_brief: concise paragraph with explicit dimensions/tolerances where known (≥10 chars).\n"
        "questions       : list of up to 3 highest-leverage questions that unblock modeling.\n"
        "  - Return an empty question list when the goal, assumptions, and user answers already provide enough detail to sketch and dimension the next feature.\n"
        "  - Include material/layer-height/nozzle values if missing from assumptions.\n"
        "  - Include critical fit/clearance targets if unspecified.\n"
        "  - Do not ask questions already answered above."
    )

    result = await _run_structured_agent(
        system_prompt=(
            "## ROLE\n"
            "You are a CAD planning assistant applying the Printer-Profile-Tolerancing skill.\n"
            "Normalize goals into manufacturing-ready language with explicit tolerance/clearance "
            "targets (e.g. '0.30 mm mating clearance', '0.2 mm layer height'). "
            "Ask only the highest-leverage questions that unblock the SolidWorks modeling steps. "
            "Always surface material, nozzle size, and orientation constraints when present in the goal. "
            "If the user has already supplied explicit dimensions, wall thickness, fit targets, and feature placement, do not keep restating the same asks; return zero questions instead."
        ),
        user_prompt=prompt,
        result_type=ClarificationResponse,
        model_name=resolved_model,
        local_endpoint=resolved_endpoint,
    )

    if isinstance(result, RecoverableFailure):
        merge_metadata(
            session_id,
            db_path=db_path,
            latest_message=result.explanation,
            clarifying_questions=[],
            latest_error_text=result.explanation,
            remediation_hint=(
                result.remediation_steps[0]
                if result.remediation_steps
                else "Configure provider credentials and retry."
            ),
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.request_clarifications",
            input_json=json.dumps({"user_goal": user_goal}, ensure_ascii=True),
            output_json=result.model_dump_json(),
            success=False,
            db_path=db_path,
        )
        return build_dashboard_state(session_id, db_path=db_path)

    metadata = merge_metadata(
        session_id,
        db_path=db_path,
        user_goal=user_goal,
        normalized_brief=result.normalized_brief,
        clarifying_questions=result.questions,
        user_clarification_answer=user_answer,
        latest_message="Generated clarifying questions from GitHub Copilot.",
        latest_error_text="",
        remediation_hint="",
    )
    insert_tool_call_record(
        session_id=session_id,
        tool_name="ui.request_clarifications",
        input_json=json.dumps({"user_goal": user_goal}, ensure_ascii=True),
        output_json=result.model_dump_json(),
        success=True,
        db_path=db_path,
    )
    insert_evidence_link(
        session_id=session_id,
        source_type="llm",
        source_id="clarification_response",
        relevance_score=0.9,
        rationale="Normalized brief and follow-up questions from GitHub Copilot.",
        payload_json=json.dumps(metadata, ensure_ascii=True),
        db_path=db_path,
    )
    return build_dashboard_state(session_id, db_path=db_path)


async def inspect_family(
    session_id: str,
    user_goal: str,
    *,
    db_path: Path | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Run LLM-backed family classification and suggested checkpoints.

    Args:
        session_id: Dashboard session identifier.
        user_goal: Free-text description of the design intent.
        db_path: Optional SQLite path override.
        model_name: Optional provider-qualified model override.

    Returns:
        Full dashboard state payload.
    """
    from .session_service import build_dashboard_state, ensure_dashboard_session  # noqa: PLC0415

    ensure_dashboard_session(session_id, user_goal=user_goal, db_path=db_path)
    session_row = get_design_session(session_id, db_path=db_path) or {}
    meta = _parse_json_blob(session_row.get("metadata_json"))
    resolved_model = normalize_model_name_for_provider(
        model_name or meta.get("model_name"),
        provider=sanitize_ui_text(meta.get("model_provider"), "github"),
        profile=sanitize_ui_text(meta.get("model_profile"), "balanced"),
    )
    resolved_endpoint = sanitize_ui_text(
        meta.get("local_endpoint"),
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )

    local_family = meta.get("proposed_family", "") or "<not yet classified>"
    local_evidence = " | ".join(meta.get("family_evidence", [])) or "<none>"
    prompt = (
        "## TASK\n"
        "Apply the Feature-Tree-Reconstruction skill to classify the SolidWorks feature family "
        "and produce a human-reviewable checkpoint plan.\n\n"
        "## DESIGN GOAL\n"
        f"{user_goal}\n\n"
        "## MODEL CONTEXT\n"
        f"Active model path  : {meta.get('active_model_path', '') or '<none>'}\n"
        f"Active model status: {meta.get('active_model_status', '') or '<none>'}\n"
        f"Feature target refs: {meta.get('feature_target_text', '') or '<none>'}\n"
        f"Feature target status: {meta.get('feature_target_status', '') or '<none>'}\n\n"
        "## LOCAL CLASSIFIER EVIDENCE (pre-computed)\n"
        f"Family  : {local_family}\n"
        f"Evidence: {local_evidence}\n\n"
        "## REFERENCE CORPUS\n"
        f"{meta.get('rag_provenance_text', '') or '<none>'}\n\n"
        "## FEATURE-TREE RECONSTRUCTION SKILL\n"
        "Inspection sequence when model is available (use your mcp tools):\n"
        "  open_model → get_model_info → list_features(include_suppressed=True) "
        "→ get_mass_properties → classify_feature_tree\n"
        "Feature families: revolve | extrude | sheet_metal | advanced_solid | assembly | drawing | unknown\n"
        "Delegation rules:\n"
        "  - sheet_metal or advanced_solid → VBA-aware reconstruction path\n"
        "  - simple part family → direct MCP checkpoint plan\n"
        "  - assembly → component-first decomposition, part-level plan per component\n"
        "Guardrail: never reconstruct from silhouette only. "
        "If confidence is low and contradictory evidence exists, propose more inspection steps. "
        "When no model is attached, treat explicit user-supplied dimensions, named sketch phases, feature ordering, and manufacturing constraints as valid user-confirmed evidence for a conservative plan.\n\n"
        "## OUTPUT CONTRACT\n"
        "Return: family, confidence (high/medium/low), evidence[], warnings[], checkpoints[3-6].\n"
        "You must always emit at least 3 checkpoints when the prompt contains enough explicit geometry to start from an empty part, even if confidence is only low or medium.\n"
        "Each checkpoint: title, allowed_tools[] (from MCP tool catalog), rationale."
    )

    result = await _run_structured_agent(
        system_prompt=(
            "## ROLE\n"
            "You are a SolidWorks routing assistant applying the Feature-Tree-Reconstruction skill.\n"
            "Classify the feature family with evidence and confidence, then produce a safe "
            "checkpoint plan for human review.\n\n"
            "## ORCHESTRATION NOTES\n"
            "  - Inspection before planning: never produce a build plan without at least one "
            "evidence item from model inspection or user-confirmed context.\n"
            "  - Explicit user-specified dimensions, feature names, and operation ordering count as user-confirmed context when no model is attached.\n"
            "  - Propose 3-6 conservative checkpoints. Require human confirmation before each "
            "irreversible step.\n"
            "  - For sheet metal or unsupported advanced features, route to VBA-aware planning.\n"
            "  - Surface warnings when evidence is contradictory or confidence is low.\n"
            "  - Prefer 'extrude' for prompt-only parts built from named sketches and base extrusions unless stronger contrary evidence exists."
        ),
        user_prompt=prompt,
        result_type=FamilyInspection,
        model_name=resolved_model,
        local_endpoint=resolved_endpoint,
    )

    if isinstance(result, RecoverableFailure):
        ordered_features = _extract_explicit_feature_order(user_goal)
        if ordered_features:
            result = _coerce_explicit_feature_order_plan(
                user_goal,
                FamilyInspection(
                    family="extrude",
                    confidence="medium",
                    evidence=[
                        "Deterministic fallback engaged because model routing failed.",
                        "Goal includes an explicit feature-order sequence.",
                    ],
                    warnings=[
                        result.explanation,
                        "Using explicit feature-order checkpoints until model routing is healthy.",
                    ],
                    checkpoints=[],
                ),
            )
        else:
            merge_metadata(
                session_id,
                db_path=db_path,
                latest_message=result.explanation,
                latest_error_text=result.explanation,
                remediation_hint=(
                    result.remediation_steps[0]
                    if result.remediation_steps
                    else "Adjust provider/model settings, then retry inspect."
                ),
            )
            insert_tool_call_record(
                session_id=session_id,
                tool_name="ui.inspect_family",
                input_json=json.dumps({"user_goal": user_goal}, ensure_ascii=True),
                output_json=result.model_dump_json(),
                success=False,
                db_path=db_path,
            )
            return build_dashboard_state(session_id, db_path=db_path)

    result = _coerce_explicit_feature_order_plan(user_goal, result)

    evidence_payload = []
    for index, line in enumerate(result.evidence, start=1):
        insert_evidence_link(
            session_id=session_id,
            source_type="llm",
            source_id=f"family_evidence_{index}",
            relevance_score=0.85,
            rationale=line,
            payload_json=json.dumps({"family": result.family}, ensure_ascii=True),
            db_path=db_path,
        )
        evidence_payload.append(line)

    if result.checkpoints:
        replacement_rows: list[dict[str, Any]] = []
        for index, checkpoint in enumerate(result.checkpoints, start=1):
            replacement_rows.append(
                {
                    "checkpoint_index": index,
                    "title": checkpoint.title,
                    "planned_action_json": json.dumps(
                        {
                            "title": checkpoint.title,
                            "goal": checkpoint.title,
                            "tools": checkpoint.allowed_tools,
                            "rationale": checkpoint.rationale,
                            **checkpoint.execution,
                        },
                        ensure_ascii=True,
                    ),
                    "approved_by_user": index == 1,
                }
            )

        replace_plan_checkpoints(
            session_id=session_id,
            checkpoints=replacement_rows,
            db_path=db_path,
        )

    metadata = merge_metadata(
        session_id,
        db_path=db_path,
        user_goal=user_goal,
        proposed_family=result.family,
        family_confidence=result.confidence,
        family_evidence=evidence_payload,
        family_warnings=result.warnings,
        latest_message=f"Updated family classification to '{result.family}' from GitHub Copilot.",
        latest_error_text="",
        remediation_hint="",
    )
    insert_tool_call_record(
        session_id=session_id,
        tool_name="ui.inspect_family",
        input_json=json.dumps({"user_goal": user_goal}, ensure_ascii=True),
        output_json=result.model_dump_json(),
        success=True,
        db_path=db_path,
    )
    insert_evidence_link(
        session_id=session_id,
        source_type="llm",
        source_id="family_inspection",
        relevance_score=0.93,
        rationale="LLM family classification and checkpoint suggestions from GitHub Copilot.",
        payload_json=json.dumps(metadata, ensure_ascii=True),
        db_path=db_path,
    )
    return build_dashboard_state(session_id, db_path=db_path)


async def run_go_orchestration(
    session_id: str,
    *,
    user_goal: str,
    assumptions_text: str | None = None,
    user_answer: str = "",
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Run a single end-to-end pass: approve brief, update preferences, clarify, inspect.

    Args:
        session_id: Dashboard session identifier.
        user_goal: Free-text description of the design intent.
        assumptions_text: Optional manufacturing assumptions to persist.
        user_answer: Any previous answers the user has already provided.
        db_path: Optional SQLite path override.
        api_origin: Base URL of the running FastAPI server.

    Returns:
        Full dashboard state payload.
    """
    from .session_service import (  # noqa: PLC0415
        approve_design_brief,
        build_dashboard_state,
        update_ui_preferences,
    )

    try:
        goal_text = sanitize_ui_text(user_goal, DEFAULT_USER_GOAL)
        approve_design_brief(session_id, goal_text, db_path=db_path)

        session_row = get_design_session(session_id, db_path=db_path) or {}
        meta = _parse_json_blob(session_row.get("metadata_json"))
        update_ui_preferences(
            session_id,
            assumptions_text=assumptions_text,
            model_provider=str(meta.get("model_provider") or "github"),
            model_profile=str(meta.get("model_profile") or "balanced"),
            model_name=meta.get("model_name"),
            local_endpoint=meta.get("local_endpoint"),
            db_path=db_path,
        )

        await request_clarifications(
            session_id,
            goal_text,
            user_answer=user_answer,
            db_path=db_path,
        )
        await inspect_family(session_id, goal_text, db_path=db_path)

        persist_ui_action(
            session_id,
            tool_name="ui.orchestrate_go",
            db_path=db_path,
            metadata_updates={
                "orchestration_status": (
                    "Go run completed: inputs saved, clarifications refreshed, engineering review updated."
                ),
                "latest_message": "Go run completed across workflow, review, and model output lanes.",
                "latest_error_text": "",
                "remediation_hint": "",
            },
            input_payload={
                "user_goal": goal_text,
                "assumptions_text": assumptions_text,
                "user_answer": user_answer,
            },
            output_payload={
                "status": "success",
                "message": "Go orchestration completed.",
            },
        )
    except Exception as exc:
        logger.exception("[ui.run_go_orchestration] failed session_id={}", session_id)
        merge_metadata(
            session_id,
            db_path=db_path,
            orchestration_status="Go run failed.",
            latest_error_text=str(exc),
            remediation_hint="Review provider credentials/model selection and retry Go.",
        )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


# ---------------------------------------------------------------------------
# Private JSON helper (local to this module)
# ---------------------------------------------------------------------------


def _parse_json_blob(payload: str | None) -> dict[str, Any]:
    """Parse a JSON string into a dict, returning an empty dict on failure."""
    if not payload:
        return {}
    try:
        result = json.loads(payload)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
