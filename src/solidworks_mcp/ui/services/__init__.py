"""Public re-exports for the ``solidworks_mcp.ui.services`` package.

Import all public service functions from this package to maintain backward
compatibility with code that previously imported directly from
``solidworks_mcp.ui.service``.
"""

from __future__ import annotations

from ._utils import (
    DEFAULT_API_ORIGIN,
    DEFAULT_PREVIEW_ORIENTATION,
    DEFAULT_RAG_DIR,
    DEFAULT_SESSION_ID,
    DEFAULT_SOURCE_MODE,
    DEFAULT_USER_GOAL,
    DEFAULT_WORKFLOW_MODE,
    SUPPORTED_MODEL_UPLOAD_SUFFIXES,
    ensure_context_dir,
    ensure_preview_dir,
    ensure_uploaded_model_dir,
    feature_grounding_warning_text,
    feature_target_status,
    filter_docs_text,
    is_url_reference,
    materialize_uploaded_model,
    merge_metadata,
    normalize_feature_targets,
    normalize_workflow_mode,
    parse_json_blob,
    persist_ui_action,
    provider_from_model_name,
    provider_has_credentials,
    read_reference_source,
    read_reference_url,
    safe_context_name,
    sanitize_model_path_text,
    sanitize_preview_viewer_url,
    sanitize_ui_text,
    trace_json,
    trace_session_row,
    trace_tool_records,
    workflow_copy,
)
from .session_service import (
    accept_family_choice,
    approve_design_brief,
    build_dashboard_state,
    build_dashboard_trace_payload,
    ensure_dashboard_session,
    load_session_context,
    reconcile_manual_edits,
    save_session_context,
    select_workflow_mode,
    update_session_notes,
    update_ui_preferences,
)
from .llm_service import (
    ClarificationResponse,
    CheckpointCandidate,
    FamilyInspection,
    inspect_family,
    request_clarifications,
    run_go_orchestration,
)
from .checkpoint_service import execute_next_checkpoint
from .docs_service import fetch_docs_context, ingest_reference_source
from .model_service import connect_target_model, open_target_model
from .preview_service import highlight_feature, refresh_preview

__all__ = [
    # utils
    "DEFAULT_API_ORIGIN",
    "DEFAULT_PREVIEW_ORIENTATION",
    "DEFAULT_RAG_DIR",
    "DEFAULT_SESSION_ID",
    "DEFAULT_SOURCE_MODE",
    "DEFAULT_USER_GOAL",
    "DEFAULT_WORKFLOW_MODE",
    "SUPPORTED_MODEL_UPLOAD_SUFFIXES",
    "ensure_context_dir",
    "ensure_preview_dir",
    "ensure_uploaded_model_dir",
    "feature_grounding_warning_text",
    "feature_target_status",
    "filter_docs_text",
    "is_url_reference",
    "materialize_uploaded_model",
    "merge_metadata",
    "normalize_feature_targets",
    "normalize_workflow_mode",
    "parse_json_blob",
    "persist_ui_action",
    "provider_from_model_name",
    "provider_has_credentials",
    "read_reference_source",
    "read_reference_url",
    "safe_context_name",
    "sanitize_model_path_text",
    "sanitize_preview_viewer_url",
    "sanitize_ui_text",
    "trace_json",
    "trace_session_row",
    "trace_tool_records",
    "workflow_copy",
    # session
    "accept_family_choice",
    "approve_design_brief",
    "build_dashboard_state",
    "build_dashboard_trace_payload",
    "ensure_dashboard_session",
    "load_session_context",
    "reconcile_manual_edits",
    "save_session_context",
    "select_workflow_mode",
    "update_session_notes",
    "update_ui_preferences",
    # llm
    "ClarificationResponse",
    "CheckpointCandidate",
    "FamilyInspection",
    "inspect_family",
    "request_clarifications",
    "run_go_orchestration",
    # checkpoint
    "execute_next_checkpoint",
    # docs
    "fetch_docs_context",
    "ingest_reference_source",
    # model
    "connect_target_model",
    "open_target_model",
    # preview
    "highlight_feature",
    "refresh_preview",
]
