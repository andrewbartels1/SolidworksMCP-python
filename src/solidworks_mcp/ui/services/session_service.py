"""Session management and dashboard state assembly for the Prefab CAD dashboard.

Responsibilities (Single Responsibility principle):
- Create and hydrate dashboard session rows.
- Persist user decisions (brief approval, family acceptance, workflow selection,
  preferences, notes, context snapshots).
- Assemble the ``DashboardUIState`` payload consumed by the Prefab UI renderer.

Does NOT own: adapter calls, LLM calls, preview export, RAG ingestion.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from ...agents.history_db import (
    get_design_session,
    insert_plan_checkpoint,
    list_evidence_links,
    list_model_state_snapshots,
    list_plan_checkpoints,
    list_tool_call_records,
    update_plan_checkpoint,
    upsert_design_session,
)
from ...config import load_config
from ..schemas import DashboardCheckpoint, DashboardEvidenceRow, DashboardUIState
from ._utils import (
    DEFAULT_API_ORIGIN,
    DEFAULT_PREVIEW_ORIENTATION,
    DEFAULT_SESSION_ID,
    DEFAULT_SOURCE_MODE,
    DEFAULT_USER_GOAL,
    DEFAULT_WORKFLOW_MODE,
    context_file_path,
    ensure_preview_dir,
    feature_grounding_warning_text,
    merge_metadata,
    normalize_model_name_for_provider,
    normalize_workflow_mode,
    parse_json_blob,
    persist_ui_action,
    provider_from_model_name,
    provider_has_credentials,
    safe_context_name,
    sanitize_model_path_text,
    sanitize_preview_viewer_url,
    sanitize_ui_text,
    trace_json,
    trace_session_row,
    trace_tool_records,
    workflow_copy,
)

# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------

_DEFAULT_CHECKPOINT_SPECS: list[dict[str, Any]] = [
    {
        "title": "Base profile",
        "goal": "Create the base sketch profile",
        "tools": ["create_sketch", "add_line"],
        "rationale": "Establish the primary profile before any 3D feature.",
    },
    {
        "title": "Extrude body",
        "goal": "Create the main body",
        "tools": ["create_extrusion"],
        "rationale": "Turn the approved sketch into the primary solid.",
    },
    {
        "title": "Hole pattern",
        "goal": "Add fastener holes and cable clearance",
        "tools": ["create_sketch", "create_cut"],
        "rationale": "Apply mounting features after the body dimensions are stable.",
    },
    {
        "title": "Clearance verify",
        "goal": "Check fit and interference",
        "tools": ["check_interference"],
        "rationale": "Validate the assembly path before release or print export.",
    },
]

_UJOINT_CHECKPOINT_SPECS: list[dict[str, Any]] = [
    {
        "title": "Reference mode selection",
        "goal": "Choose target mode (reference reproduction or print variant) and inspect constraints",
        "tools": [
            "open_model",
            "list_features",
            "create_sketch",
            "create_extrusion",
            "create_cut",
        ],
        "rationale": "Locks feature-order and dimension guardrails before generating the rest of the set.",
    },
    {
        "title": "Part set planning",
        "goal": "Generate the remaining U-joint part plans (yokes, spider, pin, crank family)",
        "tools": [
            "classify_feature_tree",
            "create_part",
            "create_sketch",
            "create_extrusion",
            "create_revolve",
        ],
        "rationale": "Decomposes U-joint into deterministic part-level steps with print-aware constraints.",
    },
    {
        "title": "Assembly build",
        "goal": "Create UJoint.SLDASM and add deterministic mates with interference checks",
        "tools": ["create_assembly", "check_interference"],
        "rationale": "Ensures mate strategy and collision checks are covered before QA.",
    },
    {
        "title": "Final quality checks",
        "goal": "Run final pass/fail checks and export preview images",
        "tools": ["list_features", "get_model_info", "export_image"],
        "rationale": "Confirms required feature trees and assembly readiness for release.",
    },
]


def _checkpoint_specs_for_goal(user_goal: str) -> list[dict[str, Any]]:
    """Select initial checkpoint template by goal text.

    Args:
        user_goal: Goal text provided by the user.

    Returns:
        List of checkpoint specification dicts.
    """
    goal = (user_goal or "").strip().lower()
    if "u-joint" in goal or "ujoint" in goal:
        return list(_UJOINT_CHECKPOINT_SPECS)
    return list(_DEFAULT_CHECKPOINT_SPECS)


def default_checkpoint_specs() -> list[dict[str, Any]]:
    """Return the four default checkpoint specs used when no LLM plan exists.

    Returns:
        List of checkpoint specification dicts.
    """
    return list(_DEFAULT_CHECKPOINT_SPECS)


def ensure_dashboard_session(
    session_id: str = DEFAULT_SESSION_ID,
    *,
    user_goal: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Ensure one dashboard session row and default checkpoints exist.

    Creates the session row on first call and inserts default checkpoints when
    none are present yet. On subsequent calls it updates the ``user_goal`` column
    when the supplied goal differs from the stored one.

    Args:
        session_id: Dashboard session identifier.
        user_goal: Optional initial or updated design goal.
        db_path: Optional override for the SQLite database path.

    Returns:
        The current session row dict.
    """
    session_row = get_design_session(session_id, db_path=db_path)
    requested_goal = sanitize_ui_text(user_goal, "") if user_goal is not None else ""
    if session_row is None:
        upsert_design_session(
            session_id=session_id,
            user_goal=requested_goal or DEFAULT_USER_GOAL,
            source_mode=DEFAULT_SOURCE_MODE,
            status="inspect",
            metadata_json=json.dumps(
                {
                    "normalized_brief": requested_goal or DEFAULT_USER_GOAL,
                    "preview_orientation": DEFAULT_PREVIEW_ORIENTATION,
                },
                ensure_ascii=True,
            ),
            db_path=db_path,
        )
    elif requested_goal and requested_goal != session_row["user_goal"]:
        upsert_design_session(
            session_id=session_id,
            user_goal=requested_goal,
            source_mode=session_row["source_mode"],
            accepted_family=session_row["accepted_family"],
            status=session_row["status"],
            current_checkpoint_index=session_row["current_checkpoint_index"],
            metadata_json=session_row["metadata_json"],
            db_path=db_path,
        )

    checkpoints = list_plan_checkpoints(session_id, db_path=db_path)
    if not checkpoints:
        base_goal = (
            requested_goal or session_row.get("user_goal") if session_row else ""
        )
        for index, spec in enumerate(
            _checkpoint_specs_for_goal(str(base_goal)), start=1
        ):
            insert_plan_checkpoint(
                session_id=session_id,
                checkpoint_index=index,
                title=spec["title"],
                planned_action_json=json.dumps(spec, ensure_ascii=True),
                approved_by_user=index == 1,
                db_path=db_path,
            )

    return get_design_session(session_id, db_path=db_path) or {}


# ---------------------------------------------------------------------------
# User-facing state mutation functions
# ---------------------------------------------------------------------------


def approve_design_brief(
    session_id: str,
    user_goal: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Persist the accepted design goal and return updated dashboard state.

    Args:
        session_id: Dashboard session identifier.
        user_goal: Design goal text approved by the user.
        db_path: Optional override for the SQLite database path.

    Returns:
        Full dashboard state payload.
    """
    ensure_dashboard_session(session_id, user_goal=user_goal, db_path=db_path)
    persist_ui_action(
        session_id,
        tool_name="ui.approve_brief",
        db_path=db_path,
        user_goal=user_goal,
        metadata_updates={
            "normalized_brief": user_goal,
            "latest_message": "Brief accepted.",
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={"user_goal": user_goal},
        output_metadata=True,
    )
    return build_dashboard_state(session_id, db_path=db_path)


def accept_family_choice(
    session_id: str,
    family: str | None = None,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Accept the proposed family classification and advance session status.

    Args:
        session_id: Dashboard session identifier.
        family: Family name to accept; falls back to ``proposed_family`` in metadata.
        db_path: Optional override for the SQLite database path.

    Returns:
        Full dashboard state payload.
    """
    session_row = ensure_dashboard_session(session_id, db_path=db_path)
    metadata = parse_json_blob(session_row.get("metadata_json"))
    accepted_family = family or metadata.get("proposed_family") or "unknown"
    upsert_design_session(
        session_id=session_id,
        user_goal=session_row.get("user_goal") or DEFAULT_USER_GOAL,
        source_mode=session_row.get("source_mode") or DEFAULT_SOURCE_MODE,
        accepted_family=accepted_family,
        status="planned",
        current_checkpoint_index=session_row.get("current_checkpoint_index") or 0,
        metadata_json=session_row.get("metadata_json"),
        db_path=db_path,
    )
    persist_ui_action(
        session_id,
        tool_name="ui.accept_family",
        db_path=db_path,
        metadata_updates={
            "accepted_family": accepted_family,
            "latest_message": f"Family accepted: {accepted_family}.",
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={"family": accepted_family},
    )
    return build_dashboard_state(session_id, db_path=db_path)


def reconcile_manual_edits(
    session_id: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Compare the two most-recent snapshots and summarise any detected changes.

    Args:
        session_id: Dashboard session identifier.
        db_path: Optional override for the SQLite database path.

    Returns:
        Full dashboard state payload.
    """
    ensure_dashboard_session(session_id, db_path=db_path)
    snapshots = list_model_state_snapshots(session_id, db_path=db_path)

    if len(snapshots) < 2:
        message = (
            "Not enough snapshots yet. Capture another preview after manual edits."
        )
    else:
        latest = snapshots[0]
        previous = snapshots[1]
        changed = latest.get("state_fingerprint") != previous.get(
            "state_fingerprint"
        ) or latest.get("screenshot_path") != previous.get("screenshot_path")
        message = (
            "Detected manual changes. Options: accept edits, patch toward goal, or rollback."
            if changed
            else "No visual/state change detected since the last accepted snapshot."
        )

    persist_ui_action(
        session_id,
        tool_name="ui.reconcile_manual_edits",
        db_path=db_path,
        metadata_updates={"latest_message": message},
        output_payload={"message": message},
    )
    return build_dashboard_state(session_id, db_path=db_path)


def update_ui_preferences(
    session_id: str,
    *,
    assumptions_text: str | None = None,
    model_provider: str | None = None,
    model_profile: str | None = None,
    model_name: str | None = None,
    local_endpoint: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Persist manufacturing assumptions and LLM provider preferences.

    Args:
        session_id: Dashboard session identifier.
        assumptions_text: Free-form manufacturing assumption text.
        model_provider: LLM provider identifier (``"github"``, ``"openai"``, etc.).
        model_profile: Capability tier (``"small"``, ``"balanced"``, ``"large"``).
        model_name: Explicit provider-qualified model name override.
        local_endpoint: Ollama / local API base URL.
        db_path: Optional override for the SQLite database path.

    Returns:
        Full dashboard state payload.
    """
    import os  # local import to keep module-level deps minimal

    ensure_dashboard_session(session_id, db_path=db_path)
    provider = (model_provider or "github").strip().lower()
    profile = (model_profile or "balanced").strip().lower()
    resolved_model = normalize_model_name_for_provider(
        model_name,
        provider=provider,
        profile=profile,
    )
    resolved_endpoint = sanitize_ui_text(
        local_endpoint,
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )
    persist_ui_action(
        session_id,
        tool_name="ui.update_preferences",
        db_path=db_path,
        metadata_updates={
            "assumptions_text": sanitize_ui_text(
                assumptions_text,
                "No assumptions provided yet.",
            ),
            "model_provider": provider,
            "model_profile": profile,
            "model_name": resolved_model,
            "local_endpoint": resolved_endpoint,
            "latest_message": "Updated assumptions and model preferences.",
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={
            "assumptions_text": assumptions_text,
            "model_provider": provider,
            "model_profile": profile,
            "model_name": resolved_model,
            "local_endpoint": resolved_endpoint,
        },
        output_metadata=True,
    )
    return build_dashboard_state(session_id, db_path=db_path)


def select_workflow_mode(
    session_id: str,
    *,
    workflow_mode: str,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Persist the onboarding workflow branch and reset new-design state when switching.

    Selecting ``"new_design"`` resets all model-attachment, preview, and clarification
    state so the user starts with a blank slate for the new part.

    Args:
        session_id: Dashboard session identifier.
        workflow_mode: Target mode (``"edit_existing"`` or ``"new_design"``).
        db_path: Optional override for the SQLite database path.

    Returns:
        Full dashboard state payload.
    """
    session_row = ensure_dashboard_session(session_id, db_path=db_path)
    normalized_mode = normalize_workflow_mode(workflow_mode)
    workflow_label, workflow_guidance, _ = workflow_copy(normalized_mode)

    if normalized_mode == "new_design":
        metadata = parse_json_blob(session_row.get("metadata_json"))
        metadata.update(
            {
                "workflow_mode": normalized_mode,
                "active_model_path": "",
                "active_model_status": "No active model connected yet.",
                "active_model_type": "",
                "active_model_configuration": "",
                "feature_target_text": "",
                "feature_target_status": "No grounded feature target selected.",
                "selected_feature_name": "",
                "selected_feature_selector_name": "",
                "preview_viewer_url": "",
                "preview_view_urls": {},
                "preview_status": "No preview captured yet.",
                "preview_stl_ready": False,
                "preview_png_ready": False,
                "clarifying_questions": [],
                "user_clarification_answer": "",
                "proposed_family": "unclassified",
                "family_confidence": "pending",
                "family_evidence": [],
                "family_warnings": [],
                "mocked_tools": [],
                "rag_source_path": "",
                "rag_status": "No retrieval source ingested yet.",
                "rag_index_path": "",
                "rag_chunk_count": 0,
                "rag_provenance_text": "No retrieval provenance available yet.",
                "docs_context_text": "No docs context loaded yet.",
                "notes_text": "",
                "orchestration_status": "Ready.",
                "context_save_status": "",
                "context_load_status": "",
                "latest_message": f"Workflow selected: {workflow_label}.",
                "latest_error_text": "",
                "remediation_hint": "",
                "normalized_brief": "Describe the new part you want to design.",
            }
        )
        upsert_design_session(
            session_id=session_id,
            user_goal="Describe the new part you want to design.",
            source_mode=session_row.get("source_mode") or DEFAULT_SOURCE_MODE,
            accepted_family=None,
            status="inspect",
            current_checkpoint_index=0,
            metadata_json=json.dumps(metadata, ensure_ascii=True),
            db_path=db_path,
        )
        # Reset all checkpoints so Execute Next starts clean for the new design.
        for row in list_plan_checkpoints(session_id, db_path=db_path):
            update_plan_checkpoint(
                int(row.get("id") or 0),
                approved_by_user=False,
                executed=False,
                result_json="",
                db_path=db_path,
            )
    else:
        metadata = merge_metadata(
            session_id,
            db_path=db_path,
            workflow_mode=normalized_mode,
            latest_message=f"Workflow selected: {workflow_label}.",
            latest_error_text="",
            remediation_hint="",
        )

    persist_ui_action(
        session_id,
        tool_name="ui.select_workflow_mode",
        db_path=db_path,
        input_payload={"workflow_mode": normalized_mode},
        output_payload={
            "workflow_mode": normalized_mode,
            "workflow_label": workflow_label,
            "workflow_guidance_text": workflow_guidance,
            "metadata": metadata,
        },
    )
    return build_dashboard_state(session_id, db_path=db_path)


def update_session_notes(
    session_id: str,
    *,
    notes_text: str,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Persist free-form engineering notes in session metadata.

    Args:
        session_id: Dashboard session identifier.
        notes_text: Free-text engineering notes content.
        db_path: Optional override for the SQLite database path.
        api_origin: API origin used for URL generation in the returned state.

    Returns:
        Full dashboard state payload.
    """
    persist_ui_action(
        session_id,
        tool_name="ui.notes.update",
        db_path=db_path,
        metadata_updates={
            "notes_text": notes_text,
            "latest_message": "Notes saved.",
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={"notes_text": notes_text},
    )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


def save_session_context(
    session_id: str,
    *,
    context_name: str | None = None,
    db_path: Path | None = None,
    context_dir: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Persist the current dashboard state to a plain JSON snapshot file.

    The snapshot can later be loaded with :func:`load_session_context` to restore
    the same session state across restarts or share it between machines.

    Args:
        session_id: Dashboard session identifier.
        context_name: Optional human-readable name for the snapshot file.
        db_path: Optional override for the SQLite database path.
        context_dir: Override directory for context snapshot files.
        api_origin: API origin used for URL generation.

    Returns:
        Full dashboard state payload.
    """
    state = build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)
    target_path = context_file_path(
        session_id,
        context_name=context_name,
        context_dir=context_dir,
    )
    payload = {
        "session_id": session_id,
        "saved_at": int(time.time()),
        "state": state,
    }
    target_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    message = f"Context saved to {target_path}."
    persist_ui_action(
        session_id,
        tool_name="ui.context.save",
        db_path=db_path,
        metadata_updates={
            "context_save_status": message,
            "context_name_input": safe_context_name(context_name, session_id),
            "context_file_input": str(target_path),
            "last_context_file": str(target_path),
            "latest_message": message,
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={"context_name": context_name},
        output_payload={"path": str(target_path)},
    )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


def load_session_context(
    session_id: str,
    *,
    context_file: str | None = None,
    db_path: Path | None = None,
    context_dir: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Load a previously saved context snapshot back into session metadata.

    Selectively merges the ``workflow_mode``, ``assumptions_text``, model path,
    feature targets, provider settings, notes, and docs query from the snapshot.
    Does not overwrite live execution state or checkpoint results.

    Args:
        session_id: Dashboard session identifier.
        context_file: Path to the JSON snapshot file; defaults to the canonical location.
        db_path: Optional override for the SQLite database path.
        context_dir: Override directory for context snapshot files.
        api_origin: API origin used for URL generation.

    Returns:
        Full dashboard state payload.
    """
    context_file_text = sanitize_ui_text(context_file, "")
    source_path = (
        Path(context_file_text)
        if context_file_text
        else context_file_path(session_id, context_dir=context_dir)
    )
    if not source_path.exists():
        message = f"Context load failed. File not found: {source_path}."
        merge_metadata(
            session_id,
            db_path=db_path,
            context_load_status=message,
            context_file_input=str(source_path),
            latest_error_text=message,
            remediation_hint="Save context first or provide a valid context file path.",
        )
        return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)

    try:
        snapshot_payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        message = f"Context load failed: {exc}."
        merge_metadata(
            session_id,
            db_path=db_path,
            context_load_status=message,
            context_file_input=str(source_path),
            latest_error_text=message,
            remediation_hint="Ensure the context file is valid JSON saved by this dashboard.",
        )
        return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)

    loaded_state = (
        snapshot_payload.get("state") if isinstance(snapshot_payload, dict) else {}
    )
    if not isinstance(loaded_state, dict):
        loaded_state = {}

    session_row = ensure_dashboard_session(session_id, db_path=db_path)
    metadata = parse_json_blob(session_row.get("metadata_json"))
    _RESTORABLE_KEYS = [
        "workflow_mode",
        "assumptions_text",
        "active_model_path",
        "active_model_status",
        "feature_target_text",
        "feature_target_status",
        "normalized_brief",
        "user_clarification_answer",
        "model_provider",
        "model_profile",
        "model_name",
        "local_endpoint",
        "rag_source_path",
        "rag_namespace",
        "notes_text",
        "docs_query",
        "docs_context_text",
    ]
    for key in _RESTORABLE_KEYS:
        if key in loaded_state:
            metadata[key] = loaded_state.get(key)

    upsert_design_session(
        session_id=session_id,
        user_goal=sanitize_ui_text(
            loaded_state.get("user_goal"),
            session_row.get("user_goal") or DEFAULT_USER_GOAL,
        ),
        source_mode=session_row.get("source_mode") or DEFAULT_SOURCE_MODE,
        accepted_family=(
            sanitize_ui_text(loaded_state.get("accepted_family"), "")
            or session_row.get("accepted_family")
        ),
        status=session_row.get("status") or "active",
        current_checkpoint_index=session_row.get("current_checkpoint_index") or 0,
        metadata_json=json.dumps(metadata, ensure_ascii=True),
        db_path=db_path,
    )

    message = f"Context loaded from {source_path}."
    persist_ui_action(
        session_id,
        tool_name="ui.context.load",
        db_path=db_path,
        metadata_updates={
            "context_load_status": message,
            "context_name_input": safe_context_name(source_path.stem, session_id),
            "context_file_input": str(source_path),
            "last_context_file": str(source_path),
            "latest_message": message,
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={"context_file": str(source_path)},
    )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


# ---------------------------------------------------------------------------
# Readiness check
# ---------------------------------------------------------------------------


def _compute_readiness(
    metadata: dict[str, Any],
    *,
    db_ready: bool,
) -> dict[str, Any]:
    """Compute the four readiness signals used by the status badge row.

    Args:
        metadata: Session metadata dict.
        db_ready: Whether the session database row was found.

    Returns:
        Dict with ``readiness_*`` keys consumed by ``DashboardUIState``.
    """
    import os  # local import

    provider = sanitize_ui_text(metadata.get("model_provider"), "").lower()
    model_name = normalize_model_name_for_provider(
        metadata.get("model_name"),
        provider=provider or None,
        profile=sanitize_ui_text(metadata.get("model_profile"), "balanced"),
    )
    local_endpoint = sanitize_ui_text(
        metadata.get("local_endpoint"),
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )

    provider_configured = provider_has_credentials(model_name, local_endpoint)

    try:
        config = load_config()
        adapter_mode = str(getattr(config.adapter_type, "value", config.adapter_type))
    except Exception:
        adapter_mode = "unknown"

    preview_dir = ensure_preview_dir()
    import os as _os

    preview_ready = preview_dir.exists() and _os.access(preview_dir, _os.W_OK)

    checks = {
        "provider": provider_configured,
        "adapter": adapter_mode != "unknown",
        "preview": preview_ready,
        "db": db_ready,
    }
    ready_count = sum(1 for v in checks.values() if v)
    summary = (
        f"Readiness {ready_count}/4 | provider={provider_configured} | "
        f"adapter={adapter_mode} | preview={preview_ready} | db={db_ready}"
    )

    return {
        "readiness_provider_configured": provider_configured,
        "readiness_adapter_mode": adapter_mode,
        "readiness_preview_ready": preview_ready,
        "readiness_db_ready": db_ready,
        "readiness_summary": summary,
    }


# ---------------------------------------------------------------------------
# State assembly
# ---------------------------------------------------------------------------

# Feature-tree metadata entry names / types to strip from the UI table.
_META_NAMES = frozenset(
    {
        "sensors",
        "annotations",
        "history",
        "design binder",
        "solid bodies",
        "surface bodies",
        "lights, cameras and scene",
        "equations",
        "favorites",
        "selection sets",
        "3d views",
    }
)
_META_TYPES = frozenset(
    {
        "sensorfolder",
        "annotationfolder",
        "historyfolder",
        "designbinder",
        "solidbodyfolder",
        "surfacebodyfolder",
        "lightsfolder",
        "mategroup",
    }
)


def _planned_tools(planned: dict[str, Any]) -> list[str]:
    """Extract the tool-name list from a checkpoint planned-action dict.

    Args:
        planned: Parsed planned-action JSON dict.

    Returns:
        List of tool name strings.
    """
    tools = planned.get("tools", [])
    return [str(tool) for tool in tools] if isinstance(tools, list) else []


def _build_checkpoint_rows(
    session_id: str,
    *,
    db_path: Path | None,
    is_new_design_clean: bool,
) -> list[dict[str, Any]]:
    """Assemble the checkpoint list for the dashboard state payload.

    Args:
        session_id: Dashboard session identifier.
        db_path: Optional SQLite override.
        is_new_design_clean: Whether this is a fresh new-design session.

    Returns:
        List of :class:`DashboardCheckpoint` dicts.
    """
    checkpoints: list[dict[str, Any]] = []
    for row in list_plan_checkpoints(session_id, db_path=db_path):
        planned = parse_json_blob(row["planned_action_json"])
        result_payload = parse_json_blob(row.get("result_json"))
        if result_payload.get("status") == "error":
            status = "failed"
        elif row["executed"]:
            status = "executed"
        elif row["approved_by_user"]:
            status = "approved"
        else:
            status = "queued"

        if is_new_design_clean and not row["executed"]:
            status = "queued"

        mocked_tools = result_payload.get("mocked_tools", [])
        tools_text = ", ".join(_planned_tools(planned))
        if mocked_tools:
            tools_text = f"{tools_text} [MOCKED: {', '.join(mocked_tools)}]"

        checkpoints.append(
            DashboardCheckpoint(
                step=str(row["checkpoint_index"]),
                goal=planned.get("goal") or row["title"],
                tools=tools_text,
                status=status,
            ).model_dump()
        )
    return checkpoints


def _build_evidence_rows(
    session_id: str,
    *,
    db_path: Path | None,
    active_model_path: str,
    is_new_design_clean: bool,
) -> list[dict[str, Any]]:
    """Assemble the filtered evidence-link rows for the dashboard state payload.

    Args:
        session_id: Dashboard session identifier.
        db_path: Optional SQLite override.
        active_model_path: Currently attached model path.
        is_new_design_clean: Whether this is a fresh new-design session.

    Returns:
        List of :class:`DashboardEvidenceRow` dicts.
    """
    if is_new_design_clean:
        return []

    all_evidence = list_evidence_links(session_id, db_path=db_path)
    model_scoped_sources = {"active_model", "feature_target"}

    filtered_evidence: list[dict[str, Any]] = []
    for evidence in all_evidence:
        source_type = str(evidence.get("source_type") or "")
        source_id = str(evidence.get("source_id") or "")
        if (
            source_type in model_scoped_sources
            and active_model_path
            and source_id
            and source_id != active_model_path
        ):
            continue
        filtered_evidence.append(evidence)

    # Collapse feature-target rows to show only the latest so the table reflects
    # the current target rather than stale historical misses.
    latest_feature_target: dict[str, Any] | None = None
    compact_evidence: list[dict[str, Any]] = []
    for evidence in filtered_evidence:
        if str(evidence.get("source_type") or "") == "feature_target":
            latest_feature_target = evidence
            continue
        compact_evidence.append(evidence)
    if latest_feature_target is not None:
        compact_evidence.append(latest_feature_target)

    rows: list[dict[str, Any]] = []
    for evidence in compact_evidence[-6:]:
        rows.append(
            DashboardEvidenceRow(
                source=evidence["source_type"],
                detail=evidence["rationale"] or evidence["source_id"],
                score=(
                    f"{evidence['relevance_score']:.2f}"
                    if evidence["relevance_score"] is not None
                    else "-"
                ),
            ).model_dump()
        )
    return rows


def _build_feature_tree(
    session_id: str,
    *,
    db_path: Path | None,
    is_new_design_clean: bool,
    selected_feature_name: str,
) -> list[dict[str, Any]]:
    """Load and filter the feature tree from the most recent snapshot.

    Args:
        session_id: Dashboard session identifier.
        db_path: Optional SQLite override.
        is_new_design_clean: When ``True``, returns an empty list.
        selected_feature_name: Currently selected feature (adds ``_selected`` marker).

    Returns:
        List of feature tree row dicts.
    """
    if is_new_design_clean:
        return []

    feature_tree_items: list[dict[str, Any]] = []
    for snap in list_model_state_snapshots(session_id, db_path=db_path):
        raw_tree = snap.get("feature_tree_json")
        if raw_tree:
            try:
                parsed = json.loads(raw_tree)
                if isinstance(parsed, list):
                    feature_tree_items = [
                        f
                        for f in parsed
                        if f.get("name", "").lower() not in _META_NAMES
                        and f.get("type", "").lower() not in _META_TYPES
                    ]
                    break
            except Exception:
                pass

    if selected_feature_name:
        feature_tree_items = [
            {**f, "_selected": "●" if f.get("name") == selected_feature_name else ""}
            for f in feature_tree_items
        ]
    return feature_tree_items


def build_dashboard_state(
    session_id: str = DEFAULT_SESSION_ID,
    *,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Assemble the complete dashboard payload consumed by the Prefab UI renderer.

    This function is the single read-path for all UI state: it reads the session
    database, merges every sub-component (checkpoints, evidence, snapshots, preview
    URLs, provider readiness), and returns the ``DashboardUIState`` model as a dict.

    Args:
        session_id: Dashboard session identifier.
        db_path: Optional override for the SQLite database path.
        api_origin: Base URL used to construct preview and viewer URLs.

    Returns:
        ``DashboardUIState`` model dumped to a plain dict.
    """
    import os  # local import

    session_row = ensure_dashboard_session(session_id, db_path=db_path)
    metadata = parse_json_blob(session_row.get("metadata_json"))
    db_ready = bool(session_row)
    workflow_mode = normalize_workflow_mode(metadata.get("workflow_mode"))
    active_model_path = sanitize_model_path_text(metadata.get("active_model_path"))
    is_new_design_clean = workflow_mode == "new_design" and not active_model_path

    # --- Checkpoints ---
    checkpoints = _build_checkpoint_rows(
        session_id, db_path=db_path, is_new_design_clean=is_new_design_clean
    )
    structured_rendering_enabled = bool(checkpoints)
    checkpoints_text = (
        " | ".join(
            f"{item['step']}. {item['goal']} [{item['status']}] via {item['tools']}"
            for item in checkpoints
        )
        if checkpoints
        else "No checkpoints available yet."
    )

    # --- Evidence rows ---
    evidence_rows = _build_evidence_rows(
        session_id,
        db_path=db_path,
        active_model_path=active_model_path,
        is_new_design_clean=is_new_design_clean,
    )
    evidence_rows_text = (
        " | ".join(
            f"{item['source']}: {item['detail']} (score {item['score']})"
            for item in evidence_rows
        )
        if evidence_rows
        else "No evidence links captured yet."
    )

    # --- Tool history ---
    tool_history = list_tool_call_records(session_id, db_path=db_path)
    latest_tool = tool_history[-1]["tool_name"] if tool_history else "waiting"
    tool_history_text = trace_json(trace_tool_records(tool_history[-20:]))

    # --- Preview URL ---

    preview_url = ""
    preview_status = "No preview captured yet."
    snapshots = list_model_state_snapshots(session_id, db_path=db_path)
    latest_snapshot_path = snapshots[0].get("screenshot_path") if snapshots else None
    if latest_snapshot_path:
        preview_path = Path(latest_snapshot_path)
        if preview_path.exists():
            ts = int(preview_path.stat().st_mtime)
            preview_url = f"{api_origin}/previews/{preview_path.name}?ts={ts}"
            preview_status = (
                f"Synced from SolidWorks current view. Last file: {preview_path.name}"
            )

    # --- Feature tree ---
    selected_feature_name = str(metadata.get("selected_feature_name") or "")
    feature_tree_items = _build_feature_tree(
        session_id,
        db_path=db_path,
        is_new_design_clean=is_new_design_clean,
        selected_feature_name=selected_feature_name,
    )

    # --- 3D viewer URL ---
    preview_viewer_url = sanitize_preview_viewer_url(
        metadata.get("preview_viewer_url"),
        session_id=session_id,
        api_origin=api_origin,
    )
    if (
        not preview_viewer_url
        and bool(metadata.get("preview_stl_ready"))
        and metadata.get("active_model_path")
    ):
        preview_viewer_url = (
            f"{api_origin}/api/ui/viewer/{session_id}?session_id={session_id}&t=0"
        )

    preview_status = sanitize_ui_text(metadata.get("preview_status"), preview_status)

    # --- Family / clarification ---
    family = (
        session_row.get("accepted_family")
        or metadata.get("proposed_family")
        or "unclassified"
    )
    confidence = metadata.get("family_confidence", "pending")
    evidence_text = (
        " | ".join(metadata.get("family_evidence", [])) or "No family evidence yet."
    )
    warning_text = (
        " | ".join(metadata.get("family_warnings", [])) or "No blocking warnings."
    )
    questions = metadata.get("clarifying_questions", [])
    question_text = (
        "\n".join(f"- {item}" for item in questions)
        if questions
        else "No outstanding clarification questions."
    )

    # --- Model / provider ---
    model_name = sanitize_ui_text(
        metadata.get("model_name"),
        os.getenv("SOLIDWORKS_UI_MODEL", "github:openai/gpt-4.1"),
    )
    model_provider = str(
        metadata.get("model_provider") or provider_from_model_name(model_name)
    )
    model_profile = str(metadata.get("model_profile") or "balanced")

    # --- Active model status ---
    active_model_status = sanitize_ui_text(metadata.get("active_model_status"), "")
    if active_model_path and not active_model_status:
        active_model_status = (
            f"Model path set: {Path(active_model_path).name} (connect pending)."
        )
    if not active_model_path and not active_model_status:
        active_model_status = "No active model connected yet."

    # --- Workflow copy ---
    workflow_label, workflow_guidance_text, flow_header_text = workflow_copy(
        workflow_mode, active_model_path
    )

    # --- Local model ---
    local_endpoint = sanitize_ui_text(
        metadata.get("local_endpoint"),
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )

    # --- Readiness ---
    readiness = _compute_readiness(metadata, db_ready=db_ready)

    # --- Context text ---
    active_model_name = Path(active_model_path).name if active_model_path else "<none>"
    preview_views = metadata.get("preview_view_urls") or {}
    model_context_lines = [
        f"Model file: {active_model_name}",
        f"Absolute path: {active_model_path or '<none>'}",
        f"Model type: {str(metadata.get('active_model_type') or '<unknown>')}",
        f"Configuration: {str(metadata.get('active_model_configuration') or '<unknown>')}",
        f"Feature tree rows: {len(feature_tree_items)}",
        f"Selected feature: {selected_feature_name or '<none>'}",
        f"Feature targets: {str(metadata.get('feature_target_text') or '<none>')}",
        f"Preview views captured: {', '.join(sorted(preview_views.keys())) or '<none>'}",
        f"Latest preview status: {preview_status}",
    ]
    model_context_text = "\n".join(model_context_lines)
    context_summary = (
        f"{active_model_name} | {str(metadata.get('active_model_type') or 'unknown')}"
        f" | config {str(metadata.get('active_model_configuration') or '<unknown>')}"
        f" | features {len(feature_tree_items)}"
    )

    fg_warning = feature_grounding_warning_text(
        active_model_path=active_model_path,
        feature_target_text=str(metadata.get("feature_target_text") or ""),
        feature_tree_count=len(feature_tree_items),
    )

    canonical_prompt_text = "\n".join(
        [
            f"Goal: {session_row.get('user_goal') or DEFAULT_USER_GOAL}",
            f"Assumptions: {sanitize_ui_text(metadata.get('assumptions_text'), '') or '<none>'}",
            f"Active model path: {active_model_path or '<none>'}",
            f"Active model status: {active_model_status}",
            f"Feature targets: {str(metadata.get('feature_target_text') or '<none>')}",
            f"Feature target status: {str(metadata.get('feature_target_status') or '<none>')}",
            f"Accepted/proposed family: {session_row.get('accepted_family') or metadata.get('proposed_family') or '<none>'}",
            f"RAG provenance: {str(metadata.get('rag_provenance_text') or '<none>')}",
            f"Docs context: {str(metadata.get('docs_context_text') or '<none>')}",
            f"Engineering notes: {str(metadata.get('notes_text') or '<none>')}",
        ]
    )

    state = DashboardUIState(
        session_id=session_id,
        workflow_mode=workflow_mode,
        workflow_label=workflow_label,
        workflow_guidance_text=workflow_guidance_text,
        user_goal=session_row.get("user_goal") or DEFAULT_USER_GOAL,
        flow_header_text=flow_header_text,
        assumptions_text=sanitize_ui_text(
            metadata.get("assumptions_text"),
            "Assume PETG, 0.4mm nozzle, 0.2mm layers, and 0.30mm mating clearance unless overridden.",
        ),
        active_model_path=active_model_path,
        active_model_status=active_model_status,
        active_model_type=str(metadata.get("active_model_type") or ""),
        active_model_configuration=str(
            metadata.get("active_model_configuration") or ""
        ),
        feature_target_text=str(metadata.get("feature_target_text") or ""),
        feature_target_status=str(
            metadata.get("feature_target_status")
            or "No grounded feature target selected."
        ),
        feature_grounding_warning_text=fg_warning,
        normalized_brief=(
            metadata.get("normalized_brief")
            or session_row.get("user_goal")
            or DEFAULT_USER_GOAL
        ),
        clarifying_questions_text=question_text,
        proposed_family=family,
        family_confidence=confidence,
        family_evidence_text=evidence_text,
        family_warning_text=warning_text,
        accepted_family=session_row.get("accepted_family") or "",
        checkpoints=checkpoints,
        checkpoints_text=checkpoints_text,
        evidence_rows=evidence_rows,
        evidence_rows_text=evidence_rows_text,
        structured_rendering_enabled=structured_rendering_enabled,
        manual_sync_ready=False,
        preview_url=preview_url,
        preview_status=preview_status,
        preview_orientation=metadata.get(
            "preview_orientation", DEFAULT_PREVIEW_ORIENTATION
        ),
        latest_message=metadata.get("latest_message", "Ready."),
        latest_tool=latest_tool,
        latest_error_text=str(metadata.get("latest_error_text") or ""),
        remediation_hint=str(metadata.get("remediation_hint") or ""),
        model_provider=model_provider,
        model_name=model_name,
        model_profile=model_profile,
        local_endpoint=local_endpoint,
        local_model_status_text=str(
            metadata.get("local_model_status_text") or "Local model controls idle."
        ),
        local_model_busy=bool(metadata.get("local_model_busy") or False),
        local_model_available=bool(metadata.get("local_model_available") or False),
        local_model_recommended_tier=str(
            metadata.get("local_model_recommended_tier") or ""
        ),
        local_model_recommended_ollama_model=str(
            metadata.get("local_model_recommended_ollama_model") or ""
        ),
        local_model_pull_command=str(metadata.get("local_model_pull_command") or ""),
        local_model_label=str(metadata.get("local_model_label") or ""),
        rag_source_path=str(metadata.get("rag_source_path") or ""),
        rag_namespace=str(metadata.get("rag_namespace") or "engineering-reference"),
        rag_status=str(
            metadata.get("rag_status") or "No retrieval source ingested yet."
        ),
        rag_index_path=str(metadata.get("rag_index_path") or ""),
        rag_chunk_count=int(metadata.get("rag_chunk_count") or 0),
        rag_provenance_text=str(
            metadata.get("rag_provenance_text")
            or "No retrieval provenance available yet."
        ),
        docs_query=str(metadata.get("docs_query") or "SolidWorks MCP endpoints"),
        docs_context_text=str(
            metadata.get("docs_context_text") or "No docs context loaded yet."
        ),
        notes_text=str(metadata.get("notes_text") or ""),
        orchestration_status=str(metadata.get("orchestration_status") or "Ready."),
        context_save_status=str(metadata.get("context_save_status") or ""),
        context_load_status=str(metadata.get("context_load_status") or ""),
        context_name_input=str(metadata.get("context_name_input") or session_id),
        context_file_input=str(metadata.get("last_context_file") or ""),
        readiness_provider_configured=readiness["readiness_provider_configured"],
        readiness_adapter_mode=readiness["readiness_adapter_mode"],
        readiness_preview_ready=readiness["readiness_preview_ready"],
        readiness_db_ready=readiness["readiness_db_ready"],
        readiness_summary=readiness["readiness_summary"],
        context_used_pct=38,
        context_text=context_summary,
        model_context_text=model_context_text,
        canonical_prompt_text=canonical_prompt_text,
        tool_history_text=tool_history_text,
        api_origin=api_origin,
        preview_viewer_url=preview_viewer_url,
        preview_view_urls=metadata.get("preview_view_urls") or {},
        user_clarification_answer=str(metadata.get("user_clarification_answer") or ""),
        mocked_tools_text=(
            "MOCKED tools: " + ", ".join(metadata.get("mocked_tools", []))
            if metadata.get("mocked_tools")
            else ""
        ),
        feature_tree_items=feature_tree_items,
        selected_feature_name=str(metadata.get("selected_feature_name") or ""),
    ).model_dump()

    logger.debug(
        "[ui.trace.state] session_id={} model_path={} selected={} feature_rows={} preview_views={} latest_tool={}",
        session_id,
        state.get("active_model_path") or "<none>",
        state.get("selected_feature_name") or "<none>",
        len(state.get("feature_tree_items") or []),
        list((state.get("preview_view_urls") or {}).keys()),
        state.get("latest_tool") or "waiting",
    )
    return state


def build_dashboard_trace_payload(
    session_id: str = DEFAULT_SESSION_ID,
    *,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Assemble the verbose debug/trace payload for the operator trace panel.

    Includes the raw session row, full metadata, complete tool-call history, and the
    assembled ``DashboardUIState`` — all serialised to both Python dicts and
    pretty-printed JSON strings for easy inspection in the UI.

    Args:
        session_id: Dashboard session identifier.
        db_path: Optional override for the SQLite database path.
        api_origin: API origin used for URL generation.

    Returns:
        Dict with ``session_row``, ``metadata``, ``state``, and ``tool_records`` sections.
    """
    ensure_dashboard_session(session_id, db_path=db_path)
    session_row = get_design_session(session_id, db_path=db_path) or {}
    metadata = parse_json_blob(session_row.get("metadata_json"))
    state = build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)
    tool_records = trace_tool_records(
        list_tool_call_records(session_id, db_path=db_path)
    )
    session_row_payload = trace_session_row(session_row)

    payload = {
        "session_id": session_id,
        "workflow_mode": state.get("workflow_mode", DEFAULT_WORKFLOW_MODE),
        "latest_message": state.get("latest_message", "Ready."),
        "latest_error_text": state.get("latest_error_text", ""),
        "debug_summary": (
            f"workflow={state.get('workflow_mode', DEFAULT_WORKFLOW_MODE)}"
            f" | model_path={state.get('active_model_path', '') or '<none>'}"
            f" | latest_tool={state.get('latest_tool', 'waiting')}"
            f" | tool_records={len(tool_records)}"
        ),
        "session_row": session_row_payload,
        "session_row_text": trace_json(session_row_payload),
        "metadata": metadata,
        "metadata_text": trace_json(metadata),
        "state": state,
        "state_text": trace_json(state),
        "tool_records": tool_records,
        "tool_records_text": trace_json(tool_records),
    }
    logger.debug(
        "[ui.trace.snapshot] session_id={} model_path={} selected={} tool_records={} preview_views={}",
        session_id,
        state.get("active_model_path") or "<none>",
        state.get("selected_feature_name") or "<none>",
        len(tool_records),
        list((state.get("preview_view_urls") or {}).keys()),
    )
    return payload
