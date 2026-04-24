"""Shared Pydantic schemas for the interactive UI dashboard.

These models keep dashboard payloads explicit, validated, and documented so both backend
endpoints and Prefab UI state use the same contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DashboardCheckpoint(BaseModel):
    """One checkpoint row shown in the planning/status area.
    
    Attributes:
        goal (str): The goal value.
        model_config (Any): The model config value.
        status (str): The status value.
        step (str): The step value.
        tools (str): The tools value.
    """

    model_config = ConfigDict(extra="forbid")

    step: str = Field(
        default="1",
        description="Human-readable checkpoint number as a string for stable rendering.",
        min_length=1,
    )
    goal: str = Field(
        default="Define first step",
        description="Checkpoint objective users review before execution.",
        min_length=1,
    )
    tools: str = Field(
        default="create_sketch",
        description="Allowed tool summary for this checkpoint.",
        min_length=1,
    )
    status: str = Field(
        default="queued",
        description="Execution status label (queued/approved/executed/failed).",
        min_length=1,
    )


class DashboardEvidenceRow(BaseModel):
    """One evidence row shown in retrieval context.
    
    Attributes:
        detail (str): The detail value.
        model_config (Any): The model config value.
        score (str): The score value.
        source (str): The source value.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(
        default="session",
        description="Evidence source type (docs/session/tool-history/etc.).",
        min_length=1,
    )
    detail: str = Field(
        default="No evidence detail",
        description="Short evidence explanation users can audit.",
        min_length=1,
    )
    score: str = Field(
        default="-",
        description="Display score string for ranking confidence.",
        min_length=1,
    )


class DashboardUIState(BaseModel):
    """Top-level dashboard state shared between backend and Prefab UI.
    
    Field descriptions are user-facing semantics and validation intent.
    
    Attributes:
        accepted_family (str): The accepted family value.
        active_model_configuration (str): The active model configuration value.
        active_model_path (str): The active model path value.
        active_model_status (str): The active model status value.
        active_model_type (str): The active model type value.
        api_origin (str): The api origin value.
        assumptions_text (str): The assumptions text value.
        canonical_prompt_text (str): The canonical prompt text value.
        checkpoints (list[DashboardCheckpoint]): The checkpoints value.
        checkpoints_text (str): The checkpoints text value.
        clarifying_questions_text (str): The clarifying questions text value.
        context_file_input (str): The context file input value.
        context_load_status (str): The context load status value.
        context_name_input (str): The context name input value.
        context_save_status (str): The context save status value.
        context_text (str): The context text value.
        context_used_pct (int): The context used pct value.
        ctx_tick (int): The ctx tick value.
        docs_context_text (str): The docs context text value.
        docs_query (str): The docs query value.
        evidence_rows (list[DashboardEvidenceRow]): The evidence rows value.
        evidence_rows_text (str): The evidence rows text value.
        family_confidence (str): The family confidence value.
        family_evidence_text (str): The family evidence text value.
        family_warning_text (str): The family warning text value.
        feature_grounding_warning_text (str): The feature grounding warning text value.
        feature_target_status (str): The feature target status value.
        feature_target_text (str): The feature target text value.
        feature_tree_items (list[dict]): The feature tree items value.
        flow_header_text (str): The flow header text value.
        latest_error_text (str): The latest error text value.
        latest_message (str): The latest message value.
        latest_tool (str): The latest tool value.
        local_endpoint (str): The local endpoint value.
        local_model_available (bool): The local model available value.
        local_model_busy (bool): The local model busy value.
        local_model_label (str): The local model label value.
        local_model_pull_command (str): The local model pull command value.
        local_model_recommended_ollama_model (str): The local model recommended ollama model
                                                    value.
        local_model_recommended_tier (str): The local model recommended tier value.
        local_model_status_text (str): The local model status text value.
        manual_sync_ready (bool): The manual sync ready value.
        mocked_tools_text (str): The mocked tools text value.
        model_config (Any): The model config value.
        model_context_text (str): The model context text value.
        model_name (str): The model name value.
        model_path_input_chooser (str): The model path input chooser value.
        model_path_input_edit (str): The model path input edit value.
        model_profile (str): The model profile value.
        model_provider (str): The model provider value.
        normalized_brief (str): The normalized brief value.
        notes_text (str): The notes text value.
        orchestration_status (str): The orchestration status value.
        preview_orientation (str): The preview orientation value.
        preview_status (str): The preview status value.
        preview_url (str): The preview url value.
        preview_view_urls (dict[str, str]): The preview view urls value.
        preview_viewer_url (str): The preview viewer url value.
        proposed_family (str): The proposed family value.
        rag_chunk_count (int): The rag chunk count value.
        rag_index_path (str): The rag index path value.
        rag_namespace (str): The rag namespace value.
        rag_provenance_text (str): The rag provenance text value.
        rag_source_path (str): The rag source path value.
        rag_status (str): The rag status value.
        readiness_adapter_mode (str): The readiness adapter mode value.
        readiness_db_ready (bool): The readiness db ready value.
        readiness_preview_ready (bool): The readiness preview ready value.
        readiness_provider_configured (bool): The readiness provider configured value.
        readiness_summary (str): The readiness summary value.
        remediation_hint (str): The remediation hint value.
        selected_feature_name (str): The selected feature name value.
        session_id (str): The session id value.
        structured_rendering_enabled (bool): The structured rendering enabled value.
        tool_history_text (str): The tool history text value.
        uploaded_file_payloads (list[dict[str, Any]]): The uploaded file payloads value.
        user_clarification_answer (str): The user clarification answer value.
        user_goal (str): The user goal value.
        workflow_guidance_text (str): The workflow guidance text value.
        workflow_label (str): The workflow label value.
        workflow_mode (str): The workflow mode value.
    """

    model_config = ConfigDict(extra="forbid")

    ctx_tick: int = Field(
        default=0,
        ge=0,
        description="UI heartbeat counter used for context animation updates.",
    )
    session_id: str = Field(
        default="prefab-dashboard",
        min_length=1,
        description="Persistent session identifier used by backend state APIs.",
    )
    workflow_mode: str = Field(
        default="unselected",
        description="Selected onboarding workflow: unselected, edit_existing, or new_design.",
    )
    workflow_label: str = Field(
        default="Choose a workflow",
        description="Human-readable label for the currently selected workflow branch.",
    )
    workflow_guidance_text: str = Field(
        default="Choose whether you are attaching an existing SolidWorks file or starting a new design from scratch.",
        min_length=5,
        description="Short onboarding guidance shown near the workflow selector.",
    )
    user_goal: str = Field(
        default="Design a printable U-bracket assembly for cable routing with M4 hardware.",
        min_length=5,
        description="Primary user intent prompt for the design workflow.",
    )
    flow_header_text: str = Field(
        default="Goal -> Assumptions -> Clarify -> Plan -> Execute",
        min_length=5,
        description="Linear workflow breadcrumb shown at the top of the dashboard.",
    )
    assumptions_text: str = Field(
        default="Assume PETG, 0.4mm nozzle, 0.2mm layers, and 0.30mm mating clearance unless overridden.",
        min_length=5,
        description="Editable assumptions reviewed by user before planning/execution.",
    )
    active_model_path: str = Field(
        default="",
        description="Absolute path to the SolidWorks model the dashboard should inspect and modify.",
    )
    model_path_input_chooser: str = Field(
        default="",
        description="Editable draft path used by the chooser-screen attach textbox.",
    )
    model_path_input_edit: str = Field(
        default="",
        description="Editable draft path used by the edit-existing attach textbox.",
    )
    uploaded_file_payloads: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Temporary browser file-picker payloads used for existing-model attach requests.",
    )
    active_model_status: str = Field(
        default="No active model connected yet.",
        description="Status line describing the currently attached target model.",
    )
    active_model_type: str = Field(
        default="",
        description="Detected document type for the connected target model.",
    )
    active_model_configuration: str = Field(
        default="",
        description="Active configuration name for the connected target model.",
    )
    feature_target_text: str = Field(
        default="",
        description="Feature-tree target references such as @Boss-Extrude1 or @Sketch2.",
    )
    feature_target_status: str = Field(
        default="No grounded feature target selected.",
        description="Validation status for the current feature-target references.",
    )
    feature_grounding_warning_text: str = Field(
        default="",
        description="Inline warning shown when grounded feature resolution is unavailable for the current model context.",
    )
    normalized_brief: str = Field(
        default="Design a printable U-bracket assembly for cable routing with M4 hardware.",
        min_length=5,
        description="LLM-normalized brief used as canonical planning input.",
    )
    clarifying_questions_text: str = Field(
        default="No outstanding clarification questions.",
        description="Rendered clarifying questions generated by LLM analysis.",
    )
    proposed_family: str = Field(
        default="unclassified",
        description="Current proposed modeling family/classification.",
    )
    family_confidence: str = Field(
        default="pending",
        description="Confidence label for family classification.",
    )
    family_evidence_text: str = Field(
        default="No family evidence yet.",
        description="Human-readable evidence summary behind family suggestion.",
    )
    family_warning_text: str = Field(
        default="No blocking warnings.",
        description="Warnings/ambiguities surfaced before execution.",
    )
    accepted_family: str = Field(
        default="",
        description="Family accepted by user for execution routing.",
    )
    checkpoints: list[DashboardCheckpoint] = Field(
        default_factory=list,
        description="Structured checkpoint list for planning/execution workflow.",
    )
    checkpoints_text: str = Field(
        default="No checkpoints available yet.",
        description="Fallback checkpoint summary for simplified rendering modes.",
    )
    evidence_rows: list[DashboardEvidenceRow] = Field(
        default_factory=list,
        description="Structured evidence rows tied to planning decisions.",
    )
    evidence_rows_text: str = Field(
        default="No evidence links captured yet.",
        description="Fallback evidence summary for simplified rendering modes.",
    )
    structured_rendering_enabled: bool = Field(
        default=False,
        description="True when checkpoint/evidence arrays are safe to render in structured table components.",
    )
    manual_sync_ready: bool = Field(
        default=False,
        description="User signal that manual SolidWorks edits are ready to reconcile.",
    )
    preview_url: str = Field(
        default="",
        description="Rendered preview image URL (if available).",
    )
    preview_status: str = Field(
        default="No preview captured yet.",
        description="Status line for preview pipeline health and recency.",
    )
    preview_orientation: str = Field(
        default="current",
        description="Requested camera orientation for preview refresh operations.",
    )
    latest_message: str = Field(
        default="Ready.",
        description="Latest backend status message for current session actions.",
    )
    latest_tool: str = Field(
        default="waiting",
        description="Most recent tool/action name for execution trace visibility.",
    )
    mocked_tools_text: str = Field(
        default="",
        description="Notice listing mocked tools when adapter bindings are missing.",
    )
    latest_error_text: str = Field(
        default="",
        description="Inline error text for card-level visibility without relying only on toasts.",
    )
    remediation_hint: str = Field(
        default="",
        description="Suggested remediation shown next to the latest inline error.",
    )
    model_provider: str = Field(
        default="github",
        description="Current LLM provider selection for clarify/plan actions.",
    )
    model_name: str = Field(
        default="github:openai/gpt-4.1",
        min_length=3,
        description="Fully-qualified model identifier used for pydantic-ai calls.",
    )
    model_profile: str = Field(
        default="balanced",
        description="Local-model sizing profile (small/balanced/large).",
    )
    local_endpoint: str = Field(
        default="http://127.0.0.1:11434/v1",
        min_length=5,
        description="OpenAI-compatible local endpoint for local model routing.",
    )
    local_model_status_text: str = Field(
        default="Local model controls idle.",
        description="Operator-facing status for local-model probe and pull actions.",
    )
    local_model_busy: bool = Field(
        default=False,
        description="Whether a local-model probe or pull action is currently in flight.",
    )
    local_model_available: bool = Field(
        default=False,
        description="Whether Ollama responded successfully to probe.",
    )
    local_model_recommended_tier: str = Field(
        default="",
        description="Recommended local model tier reported by the probe endpoint.",
    )
    local_model_recommended_ollama_model: str = Field(
        default="",
        description="Recommended Ollama model tag reported by the probe endpoint.",
    )
    local_model_pull_command: str = Field(
        default="",
        description="Recommended Ollama pull command from probe results.",
    )
    local_model_label: str = Field(
        default="",
        description="Human-readable label for the currently recommended local model.",
    )
    rag_source_path: str = Field(
        default="",
        description="Local path or http/https URL for BYO retrieval ingestion, such as a PDF, HTML article, or markdown guide.",
    )
    rag_namespace: str = Field(
        default="engineering-reference",
        min_length=1,
        description="Namespace used when storing chunks for a user-provided retrieval corpus.",
    )
    rag_status: str = Field(
        default="No retrieval source ingested yet.",
        description="Status message for the latest BYO retrieval ingestion run.",
    )
    rag_index_path: str = Field(
        default="",
        description="Filesystem path of the generated retrieval index for user-provided content.",
    )
    rag_chunk_count: int = Field(
        default=0,
        ge=0,
        description="Number of chunks produced for the current BYO retrieval corpus.",
    )
    rag_provenance_text: str = Field(
        default="No retrieval provenance available yet.",
        description="Condensed provenance summary for the latest ingested retrieval corpus.",
    )
    docs_query: str = Field(
        default="SolidWorks MCP endpoints",
        description="Search phrase used when fetching docs context from the docs endpoint.",
    )
    docs_context_text: str = Field(
        default="No docs context loaded yet.",
        description="Filtered docs excerpt shown in the docs pane under the model viewer.",
    )
    notes_text: str = Field(
        default="",
        description="User-authored engineering notes stored with the session.",
    )
    orchestration_status: str = Field(
        default="Ready.",
        description="Status line for the global Go orchestration action.",
    )
    context_save_status: str = Field(
        default="",
        description="Result message for the latest save-context action.",
    )
    context_load_status: str = Field(
        default="",
        description="Result message for the latest load-context action.",
    )
    context_name_input: str = Field(
        default="prefab-dashboard",
        description="Draft file-name token used by the save-context button.",
    )
    context_file_input: str = Field(
        default="",
        description="Draft file path used by the load-context button.",
    )
    readiness_provider_configured: bool = Field(
        default=False,
        description="Whether credentials/config exist for selected model provider.",
    )
    readiness_adapter_mode: str = Field(
        default="unknown",
        description="Detected SolidWorks adapter mode (pywin32/mock/vba).",
    )
    readiness_preview_ready: bool = Field(
        default=False,
        description="Whether preview export directory is writable and available.",
    )
    readiness_db_ready: bool = Field(
        default=True,
        description="Whether dashboard session persistence is reachable.",
    )
    readiness_summary: str = Field(
        default="Readiness not computed yet.",
        description="Condensed readiness status line for UX troubleshooting.",
    )
    context_used_pct: int = Field(
        default=38,
        ge=0,
        le=100,
        description="Approximate context budget utilization percentage.",
    )
    context_text: str = Field(
        default="76k / 200k tokens",
        description="Human-readable context budget string for the UI meter.",
    )
    model_context_text: str = Field(
        default="No active model context yet.",
        description="Structured summary of the currently attached local SolidWorks model.",
    )
    canonical_prompt_text: str = Field(
        default="",
        description="Canonical operator-facing prompt assembled from the active dashboard state.",
    )
    tool_history_text: str = Field(
        default="[]",
        description="Recent MCP/tool execution history rendered as trace JSON for operator review.",
    )
    preview_viewer_url: str = Field(
        default="",
        description="URL for the embedded Three.js 3D viewer iframe (changes with each refresh to force reload).",
    )
    preview_view_urls: dict[str, str] = Field(
        default_factory=dict,
        description="Per-orientation PNG URLs keyed by orientation name (isometric, front, top, right).",
    )
    user_clarification_answer: str = Field(
        default="",
        description="User-typed answers or clarifications in response to LLM-generated questions.",
    )
    api_origin: str = Field(
        default="http://127.0.0.1:8766",
        description="Backend origin that Prefab UI is expected to call.",
    )
    feature_tree_items: list[dict] = Field(
        default_factory=list,
        description="Feature tree rows from the active model (name, type, suppressed, position).",
    )
    selected_feature_name: str = Field(
        default="",
        description="Name of the feature most recently highlighted in SolidWorks.",
    )
