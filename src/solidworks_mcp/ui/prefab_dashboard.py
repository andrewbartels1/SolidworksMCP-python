"""Prefab dashboard for the interactive SolidWorks assistant.

Control-to-endpoint mapping and operator guidance live in:
- docs/getting-started/prefab-ui-dashboard.md
- docs/getting-started/prefab-ui-controls-reference.md
"""

from __future__ import annotations

import os
from typing import Any

from prefab_ui import PrefabApp
from prefab_ui.actions import Fetch, SetInterval, SetState, ShowToast
from prefab_ui.components import (
    Accordion,
    AccordionItem,
    Badge,
    Button,
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
    Column,
    DataTable,
    DataTableColumn,
    Embed,
    Grid,
    GridItem,
    Image,
    Muted,
    Row,
    Text,
    Textarea,
)
from prefab_ui.components.control_flow import Else, If
from prefab_ui.rx import EVENT, RESULT, STATE, Rx

from solidworks_mcp.ui.schemas import DashboardUIState

API_ORIGIN = os.getenv("SOLIDWORKS_UI_API_ORIGIN", "http://127.0.0.1:8766")
SESSION_ID_EXPR = "{{ session_id || 'prefab-dashboard' }}"

ctx_tick = Rx("ctx_tick")
ctx_pct = (ctx_tick % 24) * 3 + 18
ctx_variant = (ctx_pct > 70).then(
    "destructive", (ctx_pct <= 35).then("success", "default")
)


def _result_state(key: str, fallback: object | None = None) -> object:
    value = getattr(RESULT, key)
    # Keep unit-test semantics for the lightweight stubbed _Expr object.
    if (
        fallback is not None
        and type(value).__name__ == "_Expr"
        and getattr(value, "value", None) == key
    ):
        return fallback
    return value


def _error_toast() -> ShowToast:
    return ShowToast("Request failed", variant="error")


def _refresh_state() -> Fetch:
    """Re-hydrate from canonical session state after multi-step actions."""
    return Fetch.get(
        f"{API_ORIGIN}/api/ui/state",
        params={"session_id": SESSION_ID_EXPR},
        on_success=_hydrate_from_result(),
        on_error=_error_toast(),
    )


def _refresh_preview() -> Fetch:
    """Refresh preview and hydrate from the POST result payload directly."""
    return Fetch.post(
        f"{API_ORIGIN}/api/ui/preview/refresh",
        body={"session_id": STATE.session_id, "orientation": "isometric"},
        on_success=_hydrate_from_result(),
        on_error=_error_toast(),
    )


def _open_then_connect(connect_body: dict[str, object]) -> Fetch:
    """Run full connect + preview refresh in one request for reliable attach behavior."""
    return Fetch.post(
        f"{API_ORIGIN}/api/ui/model/connect",
        body=connect_body,
        on_success=_on_attach_success(),
        on_error=ShowToast("Attach/connect request failed", variant="error"),
    )


def _on_attach_success() -> list[object]:
    """Hydrate attach results without letting the UI fall back to chooser-only state."""
    return [
        SetState("workflow_mode", "edit_existing"),
        SetState("workflow_label", "Editing Existing Part or Assembly"),
        *_hydrate_from_result(),
        _refresh_state(),
        ShowToast("Target model attached and preview refreshed"),
    ]


def _hydrate_from_result() -> list[Any]:
    state_keys = [
        "workflow_mode",
        "workflow_label",
        "workflow_guidance_text",
        "flow_header_text",
        "assumptions_text",
        "active_model_path",
        "active_model_status",
        "active_model_type",
        "active_model_configuration",
        "feature_target_text",
        "feature_target_status",
        "normalized_brief",
        "clarifying_questions_text",
        "proposed_family",
        "family_confidence",
        "family_evidence_text",
        "family_warning_text",
        "accepted_family",
        "checkpoints",
        "checkpoints_text",
        "evidence_rows",
        "evidence_rows_text",
        "structured_rendering_enabled",
        "preview_url",
        "preview_viewer_url",
        "preview_status",
        "preview_orientation",
        "latest_message",
        "latest_tool",
        "mocked_tools_text",
        "latest_error_text",
        "remediation_hint",
        "model_provider",
        "model_name",
        "model_profile",
        "local_endpoint",
        "rag_source_path",
        "rag_namespace",
        "rag_status",
        "rag_index_path",
        "rag_chunk_count",
        "rag_provenance_text",
        "docs_query",
        "docs_context_text",
        "notes_text",
        "orchestration_status",
        "context_save_status",
        "context_load_status",
        "context_name_input",
        "context_file_input",
        "model_context_text",
        "canonical_prompt_text",
        "tool_history_text",
        "readiness_provider_configured",
        "readiness_adapter_mode",
        "readiness_preview_ready",
        "readiness_db_ready",
        "readiness_summary",
        "manual_sync_ready",
        "context_text",
        "feature_tree_items",
        "selected_feature_name",
        "preview_view_urls",
    ]
    hydrated = [
        SetState(key, _result_state(key, getattr(STATE, key))) for key in state_keys
    ]
    # Mirror canonical active path into editable draft fields used by attach buttons.
    hydrated.extend(
        [
            SetState(
                "model_path_input_chooser", _result_state("active_model_path", "")
            ),
            SetState("model_path_input_edit", _result_state("active_model_path", "")),
        ]
    )
    return hydrated


with PrefabApp(
    title="SolidWorks CAD Assistant",
    state=DashboardUIState().model_dump(),
    connect_domains=[API_ORIGIN],
    on_mount=[
        _refresh_state(),
        SetInterval(500, on_tick=SetState("ctx_tick", ctx_tick + 1)),
        SetInterval(
            180000,
            on_tick=Fetch.post(
                f"{API_ORIGIN}/api/ui/preview/refresh",
                body={
                    "session_id": SESSION_ID_EXPR,
                    "orientation": STATE.preview_orientation,
                },
                on_success=_hydrate_from_result(),
            ),
        ),
    ],
) as app:
    with Column(gap=4):
        # Global operator controls (context snapshots + one-click orchestration).
        with Card():
            with CardHeader():
                with Row(cssClass="justify-between", align="center"):
                    with Column(gap=1):
                        CardTitle("SolidWorks Unified CAD & 3D Printing Assistant")
                        CardDescription(
                            "Top-right controls save/load context and run a single Go orchestration pass across all three columns."
                        )
                    with Column(gap=2):
                        with Row(gap=2):
                            Textarea(
                                name="context_name_input",
                                value=STATE.context_name_input,
                                rows=1,
                                placeholder="Context name",
                                onChange=SetState("context_name_input", EVENT),
                            )
                            Button(
                                "Save Context",
                                variant="outline",
                                size="sm",
                                on_click=Fetch.post(
                                    f"{API_ORIGIN}/api/ui/context/save",
                                    body={
                                        "session_id": STATE.session_id,
                                        "context_name": STATE.context_name_input,
                                    },
                                    on_success=[
                                        *_hydrate_from_result(),
                                        ShowToast("Context saved"),
                                    ],
                                    on_error=_error_toast(),
                                ),
                            )
                        with Row(gap=2):
                            Textarea(
                                name="context_file_input",
                                value=STATE.context_file_input,
                                rows=1,
                                placeholder="Context file path",
                                onChange=SetState("context_file_input", EVENT),
                            )
                            Button(
                                "Load Context",
                                variant="outline",
                                size="sm",
                                on_click=Fetch.post(
                                    f"{API_ORIGIN}/api/ui/context/load",
                                    body={
                                        "session_id": STATE.session_id,
                                        "context_file": STATE.context_file_input,
                                    },
                                    on_success=[
                                        *_hydrate_from_result(),
                                        ShowToast("Context loaded"),
                                    ],
                                    on_error=_error_toast(),
                                ),
                            )
                        Button(
                            "GO",
                            variant="success",
                            on_click=Fetch.post(
                                f"{API_ORIGIN}/api/ui/orchestrate/go",
                                body={
                                    "session_id": STATE.session_id,
                                    "user_goal": STATE.user_goal,
                                    "assumptions_text": STATE.assumptions_text,
                                    "user_answer": STATE.user_clarification_answer,
                                },
                                on_success=[
                                    *_hydrate_from_result(),
                                    ShowToast("Go orchestration complete"),
                                ],
                                on_error=_error_toast(),
                            ),
                        )
            with CardContent():
                with Column(gap=1):
                    Badge("{{ orchestration_status || 'Ready.' }}", variant="secondary")
                    Muted("Session id: {{ session_id }} (default is prefab-dashboard).")
                    Muted(
                        "Context name chooses the JSON filename; context file path points to a saved snapshot under .solidworks_mcp/ui_context/."
                    )
                    with If("context_save_status"):
                        Muted("{{ context_save_status }}")
                    with If("context_load_status"):
                        Muted("{{ context_load_status }}")

        with Grid(columns={"default": 1, "xl": 3}, gap=4):
            with GridItem():
                with Column(gap=4):
                    # Lane 1: workflow/model inputs that define execution intent.
                    with Card():
                        with CardHeader():
                            CardTitle("1. Workflow Inputs and Planning")
                            CardDescription(
                                "Open the file first, then connect and update planning inputs."
                            )
                        with CardContent():
                            with Column(gap=2):
                                Badge("{{ workflow_label || 'Choose a Workflow' }}")
                                Badge(
                                    "mode: {{ workflow_mode || 'unselected' }}",
                                    variant="outline",
                                )
                                Badge(
                                    "{{ flow_header_text || 'Choose Workflow -> Configure -> Inspect/Clarify -> Plan -> Execute' }}",
                                    variant="secondary",
                                )
                                Muted("{{ workflow_guidance_text }}")
                                Text("Model path")
                                Textarea(
                                    name="model_path_input_edit",
                                    value=STATE.model_path_input_edit,
                                    rows=3,
                                    onChange=SetState("model_path_input_edit", EVENT),
                                )
                                Text("Feature targets")
                                Textarea(
                                    name="feature_target_text",
                                    value=STATE.feature_target_text,
                                    rows=2,
                                    onChange=SetState("feature_target_text", EVENT),
                                )
                                Muted("{{ feature_target_status }}")
                                Muted("{{ active_model_status }}")
                        with CardFooter():
                            with Row(gap=2):
                                Button(
                                    "Attach Local Path",
                                    variant="success",
                                    size="sm",
                                    on_click=[
                                        SetState("workflow_mode", "edit_existing"),
                                        SetState(
                                            "active_model_path",
                                            STATE.model_path_input_edit,
                                        ),
                                        _open_then_connect(
                                            {
                                                "session_id": STATE.session_id,
                                                "model_path": STATE.model_path_input_edit,
                                                "feature_target_text": STATE.feature_target_text,
                                            },
                                        ),
                                    ],
                                )
                                Button(
                                    "New Design",
                                    variant="outline",
                                    size="sm",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/workflow/select",
                                        body={
                                            "session_id": STATE.session_id,
                                            "workflow_mode": "new_design",
                                        },
                                        on_success=[
                                            _refresh_state(),
                                            ShowToast("Workflow updated"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )

                    with Card():
                        with CardHeader():
                            CardTitle("Design Spec and Model Settings")
                            CardDescription(
                                "Describe the part intent, assumptions, and model routing before planning actions."
                            )
                        with CardContent():
                            with Column(gap=2):
                                Text("Design goal")
                                Muted(
                                    "What to build or modify, key dimensions, and success criteria."
                                )
                                Textarea(
                                    name="user_goal",
                                    value=STATE.user_goal,
                                    rows=4,
                                    onChange=SetState("user_goal", EVENT),
                                )
                                Text("Assumptions and manufacturing constraints")
                                Muted(
                                    "Material, layer height, tolerances/clearances, nozzle, orientation, and must-keep features."
                                )
                                Textarea(
                                    name="assumptions_text",
                                    value=STATE.assumptions_text,
                                    rows=3,
                                    onChange=SetState("assumptions_text", EVENT),
                                )
                                Text("Model provider")
                                with Row(gap=2):
                                    Button(
                                        "Provider: GitHub",
                                        variant="outline",
                                        size="sm",
                                        on_click=[
                                            SetState("model_provider", "github"),
                                            ShowToast(
                                                "Using GitHub Models. Setup docs: docs/getting-started/vscode-mcp-setup.md",
                                            ),
                                        ],
                                    )
                                    Button(
                                        "Provider: Local",
                                        variant="outline",
                                        size="sm",
                                        on_click=[
                                            SetState("model_provider", "local"),
                                            ShowToast(
                                                "Using local Ollama route. Setup docs: docs/getting-started/local-llm.md",
                                            ),
                                        ],
                                    )
                                with Row(gap=2):
                                    with If("model_provider == 'github'"):
                                        Badge(
                                            "Provider selected: github",
                                            variant="success",
                                        )
                                    with Else():
                                        Badge(
                                            "Provider selected: local",
                                            variant="secondary",
                                        )
                                Muted(
                                    "Docs quick links: /docs (API), docs/getting-started/vscode-mcp-setup.md (SolidWorks MCP), docs/getting-started/local-llm.md (Ollama/Gemma local setup)."
                                )
                                Text("Model profile")
                                with Row(gap=2):
                                    Button(
                                        "Profile: Small",
                                        variant="outline",
                                        size="sm",
                                        on_click=SetState("model_profile", "small"),
                                    )
                                    Button(
                                        "Profile: Balanced",
                                        variant="outline",
                                        size="sm",
                                        on_click=SetState("model_profile", "balanced"),
                                    )
                                    Button(
                                        "Profile: Large",
                                        variant="outline",
                                        size="sm",
                                        on_click=SetState("model_profile", "large"),
                                    )
                                Badge(
                                    "Profile selected: {{ model_profile || 'balanced' }}",
                                    variant="outline",
                                )
                                Text("Model name")
                                Muted(
                                    "Provider-qualified name is recommended (for example github:openai/gpt-4.1 or local:google/gemma-3-12b-it)."
                                )
                                Textarea(
                                    name="model_name",
                                    value=STATE.model_name,
                                    rows=2,
                                    onChange=SetState("model_name", EVENT),
                                )
                                Text("Local endpoint (only used for provider=local)")
                                Textarea(
                                    name="local_endpoint",
                                    value=STATE.local_endpoint,
                                    rows=2,
                                    onChange=SetState("local_endpoint", EVENT),
                                )
                        with CardFooter():
                            with Row(gap=2):
                                Button(
                                    "Approve Brief",
                                    variant="outline",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/brief/approve",
                                        body={
                                            "session_id": STATE.session_id,
                                            "user_goal": STATE.user_goal,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("Brief approved"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )
                                Button(
                                    "Save Preferences",
                                    variant="success",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/preferences/update",
                                        body={
                                            "session_id": STATE.session_id,
                                            "assumptions_text": STATE.assumptions_text,
                                            "model_provider": STATE.model_provider,
                                            "model_profile": STATE.model_profile,
                                            "model_name": STATE.model_name,
                                            "local_endpoint": STATE.local_endpoint,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("Preferences saved"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )
                                Button(
                                    "Plan Next Steps",
                                    variant="outline",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/family/inspect",
                                        body={
                                            "session_id": STATE.session_id,
                                            "user_goal": STATE.user_goal,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("Planning refreshed"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )

            with GridItem():
                with Column(gap=4):
                    # Lane 2: clarification, review, and manual reconciliation controls.
                    with Card():
                        with CardHeader():
                            CardTitle("2. Clarification and Engineering Review")
                            CardDescription(
                                "Use this lane for Q&A and engineering acceptance."
                            )
                        with CardContent():
                            with Column(gap=2):
                                Muted("{{ clarifying_questions_text }}")
                                Textarea(
                                    name="user_clarification_answer",
                                    value=STATE.user_clarification_answer,
                                    rows=4,
                                    onChange=SetState(
                                        "user_clarification_answer", EVENT
                                    ),
                                )
                                with If("latest_error_text"):
                                    Badge(
                                        "{{ latest_error_text }}", variant="destructive"
                                    )
                                    with If("remediation_hint"):
                                        Muted("{{ remediation_hint }}")
                        with CardFooter():
                            with Row(gap=2):
                                Button(
                                    "Refresh Clarifications",
                                    variant="outline",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/clarify",
                                        body={
                                            "session_id": STATE.session_id,
                                            "user_goal": STATE.user_goal,
                                            "user_answer": STATE.user_clarification_answer,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("Clarifications updated"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )
                                Button(
                                    "Inspect More",
                                    variant="outline",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/family/inspect",
                                        body={
                                            "session_id": STATE.session_id,
                                            "user_goal": STATE.user_goal,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("Inspection updated"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )
                                Button(
                                    "Accept Approach",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/family/accept",
                                        body={
                                            "session_id": STATE.session_id,
                                            "family": STATE.proposed_family,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("Approach accepted"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )

                    with Card():
                        with CardHeader():
                            CardTitle("Engineering Signals")
                        with CardContent():
                            with Column(gap=2):
                                with Row(gap=2):
                                    Badge("{{ proposed_family }}", variant="default")
                                    Badge(
                                        f"confidence: {STATE.family_confidence}",
                                        variant="secondary",
                                    )
                                Muted("{{ family_evidence_text }}")
                                Muted("{{ family_warning_text }}")
                                with Row(gap=2):
                                    with If("readiness_provider_configured"):
                                        Badge("provider: ok", variant="success")
                                    with Else():
                                        Badge(
                                            "provider: missing", variant="destructive"
                                        )
                                    Badge(
                                        f"adapter: {STATE.readiness_adapter_mode}",
                                        variant="outline",
                                    )
                                    with If("readiness_preview_ready"):
                                        Badge("preview: ok", variant="success")
                                    with Else():
                                        Badge(
                                            "preview: not ready", variant="destructive"
                                        )
                                Muted("{{ readiness_summary }}")

                    with Card():
                        with CardHeader():
                            CardTitle("Manual Sync")
                        with CardContent():
                            with Column(gap=2):
                                with Row(gap=2):
                                    Button(
                                        "Mark Manual Edits Complete",
                                        variant="outline",
                                        size="sm",
                                        on_click=SetState("manual_sync_ready", True),
                                    )
                                    Button(
                                        "Clear Manual-Edit Flag",
                                        variant="outline",
                                        size="sm",
                                        on_click=SetState("manual_sync_ready", False),
                                    )
                                with If("manual_sync_ready"):
                                    Badge("manual sync: ready", variant="success")
                                with Else():
                                    Badge("manual sync: waiting", variant="secondary")
                                with If("manual_sync_ready"):
                                    Button(
                                        "Run Diff and Reconcile",
                                        variant="success",
                                        on_click=Fetch.post(
                                            f"{API_ORIGIN}/api/ui/manual-sync/reconcile",
                                            body={"session_id": STATE.session_id},
                                            on_success=[
                                                *_hydrate_from_result(),
                                                ShowToast("Manual sync reviewed"),
                                            ],
                                            on_error=_error_toast(),
                                        ),
                                    )

            with GridItem():
                with Column(gap=4):
                    # Lane 3: output evidence and checkpoint execution controls.
                    with Card():
                        with CardHeader():
                            CardTitle("3. Model Output")
                            CardDescription(
                                "Lane for normalized output, plan status, and evidence."
                            )
                        with CardContent():
                            with Column(gap=2):
                                Muted("{{ normalized_brief }}")
                                Muted("{{ latest_message }}")
                                Muted("latest action: {{ latest_tool }}")
                                with If("mocked_tools_text"):
                                    Badge(
                                        "{{ mocked_tools_text }}", variant="destructive"
                                    )

                    with Card():
                        with CardHeader():
                            CardTitle("Checkpoint Plan")
                        with CardContent():
                            with If("structured_rendering_enabled"):
                                DataTable(
                                    columns=[
                                        DataTableColumn(key="step", header="Step"),
                                        DataTableColumn(key="goal", header="Goal"),
                                        DataTableColumn(key="tools", header="Tools"),
                                        DataTableColumn(key="status", header="Status"),
                                    ],
                                    rows=Rx("checkpoints"),
                                    paginated=False,
                                )
                            with Else():
                                Muted("{{ checkpoints_text }}")
                        with CardFooter():
                            Button(
                                "Execute Next Checkpoint",
                                on_click=Fetch.post(
                                    f"{API_ORIGIN}/api/ui/checkpoints/execute-next",
                                    body={"session_id": STATE.session_id},
                                    on_success=[
                                        *_hydrate_from_result(),
                                        ShowToast("Checkpoint updated"),
                                    ],
                                    on_error=_error_toast(),
                                ),
                            )

                    with Card():
                        with CardHeader():
                            CardTitle("Evidence and Retrieval")
                        with CardContent():
                            with If("structured_rendering_enabled"):
                                DataTable(
                                    columns=[
                                        DataTableColumn(key="source", header="Source"),
                                        DataTableColumn(key="detail", header="Detail"),
                                        DataTableColumn(key="score", header="Score"),
                                    ],
                                    rows=Rx("evidence_rows"),
                                    paginated=False,
                                )
                            with Else():
                                Muted("{{ evidence_rows_text }}")

                    with Card():
                        with CardHeader():
                            CardTitle("Local Model Context")
                        with CardContent():
                            with Column(gap=2):
                                Muted("{{ context_text }}")
                                Textarea(
                                    name="model_context_text_view",
                                    value=STATE.model_context_text,
                                    rows=9,
                                )

        # Viewer workspace + feature selection table.
        with Card():
            with CardHeader():
                CardTitle("3D Model and Multi-View Workspace")
                CardDescription(
                    "Bottom section spans the full width for 3D, orthographic previews, and component selection."
                )
            with CardContent():
                with Grid(columns={"default": 1, "xl": 2}, gap=4):
                    with GridItem():
                        with Column(gap=2):
                            with If("preview_viewer_url"):
                                Embed(
                                    url=STATE.preview_viewer_url,
                                    width="100%",
                                    height="520px",
                                )
                            with Else():
                                with If("preview_url"):
                                    Image(
                                        src=Rx("preview_url"),
                                        alt=Rx("preview_status"),
                                        width="100%",
                                        height="520px",
                                        cssClass="border-2 border-slate-300 rounded",
                                    )
                                with Else():
                                    Muted(
                                        "No preview captured yet. Attach a model, then refresh the 3D view."
                                    )
                            Muted(
                                "View: {{ preview_orientation || 'current' }} | Status: {{ preview_status || 'No preview' }}"
                            )
                            with Row(gap=2):
                                Button(
                                    "Refresh 3D",
                                    on_click=[
                                        _refresh_preview(),
                                        ShowToast("3D view refreshed"),
                                    ],
                                )
                                for _orientation in [
                                    "isometric",
                                    "front",
                                    "top",
                                    "right",
                                    "current",
                                ]:
                                    Button(
                                        _orientation.capitalize(),
                                        variant="outline",
                                        size="sm",
                                        on_click=Fetch.post(
                                            f"{API_ORIGIN}/api/ui/preview/refresh",
                                            body={
                                                "session_id": STATE.session_id,
                                                "orientation": _orientation,
                                            },
                                            on_success=[
                                                *_hydrate_from_result(),
                                                ShowToast(
                                                    f"{_orientation} view captured"
                                                ),
                                            ],
                                            on_error=_error_toast(),
                                        ),
                                    )

                            with Grid(columns=2, gap=2):
                                for _view_name, _view_label in [
                                    ("isometric", "Isometric"),
                                    ("front", "Front"),
                                    ("top", "Top"),
                                    ("right", "Right"),
                                ]:
                                    with GridItem():
                                        Muted(_view_label)
                                        with If(f"preview_view_urls.{_view_name}"):
                                            Image(
                                                src=f"{{{{ preview_view_urls.{_view_name} }}}}",
                                                alt=f"{_view_label} view",
                                                width="100%",
                                            )
                                        with Else():
                                            Muted("No screenshot yet.")

                    with GridItem():
                        with Column(gap=2):
                            Text("Component and Feature Selection")
                            Muted(
                                "Select a row to highlight the target in SolidWorks; this keeps component selection close to the viewer."
                            )
                            with If(
                                "structured_rendering_enabled && feature_tree_items && feature_tree_items.length"
                            ):
                                DataTable(
                                    columns=[
                                        DataTableColumn(key="_selected", header=""),
                                        DataTableColumn(key="name", header="Name"),
                                        DataTableColumn(key="type", header="Type"),
                                        DataTableColumn(
                                            key="suppressed", header="Suppressed"
                                        ),
                                    ],
                                    rows=Rx("feature_tree_items"),
                                    paginated=True,
                                    onRowClick=[
                                        Fetch.post(
                                            f"{API_ORIGIN}/api/ui/feature/select",
                                            body={
                                                "session_id": STATE.session_id,
                                                "feature_name": "{{ $event.name }}",
                                            },
                                            on_success=[
                                                *_hydrate_from_result(),
                                                _refresh_preview(),
                                                ShowToast("Feature highlighted"),
                                            ],
                                            on_error=_error_toast(),
                                        )
                                    ],
                                )
                                Muted("Selected: {{ selected_feature_name || 'none' }}")
                            with Else():
                                Muted(
                                    "No feature tree data yet. Attach a model to populate this table."
                                )

        # Supplemental docs context and operator notes.
        with Card():
            with CardHeader():
                CardTitle("Docs MCP Context and Session Notes")
                CardDescription(
                    "Pane below the 3D workspace for docs endpoint context and persistent notes."
                )
            with CardContent():
                with Grid(columns={"default": 1, "xl": 2}, gap=4):
                    with GridItem():
                        with Column(gap=2):
                            Text("Docs query")
                            Textarea(
                                name="docs_query",
                                value=STATE.docs_query,
                                rows=2,
                                onChange=SetState("docs_query", EVENT),
                            )
                            Button(
                                "Refresh Docs Context",
                                variant="outline",
                                on_click=Fetch.post(
                                    f"{API_ORIGIN}/api/ui/docs/context",
                                    body={
                                        "session_id": STATE.session_id,
                                        "query": STATE.docs_query,
                                    },
                                    on_success=[
                                        *_hydrate_from_result(),
                                        ShowToast("Docs context refreshed"),
                                    ],
                                    on_error=_error_toast(),
                                ),
                            )
                            Muted("{{ docs_context_text }}")

                    with GridItem():
                        with Column(gap=2):
                            Text("Engineering notes")
                            Textarea(
                                name="notes_text",
                                value=STATE.notes_text,
                                rows=10,
                                onChange=SetState("notes_text", EVENT),
                            )
                            Button(
                                "Save Notes",
                                variant="success",
                                on_click=Fetch.post(
                                    f"{API_ORIGIN}/api/ui/notes/update",
                                    body={
                                        "session_id": STATE.session_id,
                                        "notes_text": STATE.notes_text,
                                    },
                                    on_success=[
                                        *_hydrate_from_result(),
                                        ShowToast("Notes saved"),
                                    ],
                                    on_error=_error_toast(),
                                ),
                            )

        # Operator trace panes: canonical prompt and backend tool history.
        with Card():
            with CardHeader():
                CardTitle("Operator Trace")
                CardDescription(
                    "Expandable operator panes for the canonical steering prompt and recent MCP/tool activity. LLM private thoughts are not exposed."
                )
            with CardContent():
                with Accordion(multiple=False, collapsible=True):
                    with AccordionItem("Canonical Prompt and Steering"):
                        with Column(gap=2):
                            Muted(
                                "This is the canonical prompt context assembled from the dashboard state that steers clarify, inspect, and execution actions."
                            )
                            Textarea(
                                name="canonical_prompt_text_view",
                                value=STATE.canonical_prompt_text,
                                rows=12,
                            )
                    with AccordionItem("Recent MCP Activity"):
                        with Column(gap=2):
                            Muted(
                                "Recent backend tool-call trace for this session, suitable for operator review when a button or automation step misbehaves."
                            )
                            Textarea(
                                name="tool_history_text_view",
                                value=STATE.tool_history_text,
                                rows=14,
                            )
