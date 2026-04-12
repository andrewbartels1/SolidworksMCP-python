"""Prefab dashboard for the interactive SolidWorks assistant."""

from __future__ import annotations

import os

from prefab_ui import PrefabApp
from prefab_ui.actions import Fetch, OpenFilePicker, SetInterval, SetState, ShowToast
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
    Checkbox,
    Column,
    DataTable,
    DataTableColumn,
    Embed,
    Grid,
    GridItem,
    Image,
    Muted,
    Progress,
    Row,
    Text,
    Textarea,
)
from prefab_ui.components.control_flow import Else, If
from prefab_ui.rx import ERROR, EVENT, RESULT, STATE, Rx

from solidworks_mcp.ui.schemas import DashboardUIState

API_ORIGIN = os.getenv("SOLIDWORKS_UI_API_ORIGIN", "http://127.0.0.1:8766")

ctx_tick = Rx("ctx_tick")
ctx_pct = (ctx_tick % 24) * 3 + 18
ctx_variant = (ctx_pct > 70).then(
    "destructive", (ctx_pct <= 35).then("success", "default")
)


def _result_state(key: str) -> object:
    return getattr(RESULT, key)


def _error_toast() -> ShowToast:
    return ShowToast(ERROR, variant="error")


def _hydrate_from_result() -> list[object]:
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
        "readiness_provider_configured",
        "readiness_adapter_mode",
        "readiness_preview_ready",
        "readiness_db_ready",
        "readiness_summary",
        "manual_sync_ready",
        "context_text",
    ]
    return [SetState(key, _result_state(key)) for key in state_keys]


with PrefabApp(
    title="SolidWorks CAD Assistant",
    state=DashboardUIState().model_dump(),
    connect_domains=[API_ORIGIN],
    on_mount=[
        Fetch.get(
            f"{API_ORIGIN}/api/ui/state",
            params={"session_id": STATE.session_id},
            on_success=_hydrate_from_result(),
            on_error=_error_toast(),
        ),
        SetInterval(500, on_tick=SetState("ctx_tick", ctx_tick + 1)),
        SetInterval(
            180000,
            on_tick=Fetch.post(
                f"{API_ORIGIN}/api/ui/preview/refresh",
                body={
                    "session_id": STATE.session_id,
                    "orientation": STATE.preview_orientation,
                },
                on_success=_hydrate_from_result(),
            ),
        ),
    ],
) as app:
    with If("workflow_mode == 'unselected'"):
        with Card():
            with CardHeader():
                CardTitle("Choose How To Start")
                CardDescription(
                    "Pick the branch that matches your task before opening the planning workspace."
                )
            with CardContent():
                with Grid(columns={"default": 1, "lg": 2}, gap=4):
                    with Card():
                        with CardHeader():
                            CardTitle("Edit Existing Part or Assembly")
                            CardDescription(
                                "Use this when you already have a local .sldprt or .sldasm file."
                            )
                        with CardContent():
                            Muted(
                                "Attach the model, ground feature targets, then plan modifications against that file."
                            )
                        with CardFooter():
                            Button(
                                "Use Existing Local Model",
                                variant="success",
                                on_click=OpenFilePicker(
                                    accept=".sldprt,.sldasm,.slddrw",
                                    max_size=50 * 1024 * 1024,
                                    on_success=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/model/connect",
                                        body={
                                            "session_id": STATE.session_id,
                                            "uploaded_files": EVENT,
                                            "feature_target_text": STATE.feature_target_text,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("Target model attached"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                    on_error=_error_toast(),
                                ),
                            )
                    with Card():
                        with CardHeader():
                            CardTitle("Start New Design From Scratch")
                            CardDescription(
                                "Use this when no initial model file exists and the workflow starts from requirements."
                            )
                        with CardContent():
                            Muted(
                                "Define design intent and assumptions first, then classify and execute checkpoints."
                            )
                        with CardFooter():
                            Button(
                                "Open New-Design Workflow",
                                variant="success",
                                on_click=Fetch.post(
                                    f"{API_ORIGIN}/api/ui/workflow/select",
                                    body={
                                        "session_id": STATE.session_id,
                                        "workflow_mode": "new_design",
                                    },
                                    on_success=[
                                        *_hydrate_from_result(),
                                        ShowToast("New-design workflow selected"),
                                    ],
                                    on_error=_error_toast(),
                                ),
                            )
    with Else():
        with Grid(columns={"default": 1, "xl": 3}, gap=4):
            with GridItem():
                with Column(gap=4):
                    with Card():
                        with CardHeader():
                            CardTitle("1. Workflow and Inputs")
                            CardDescription(
                                "Configure workflow, model, and requirements before planning."
                            )
                        with CardContent():
                            with Column(gap=2):
                                with If(
                                    "workflow_label and '{{' not in workflow_label and '$result' not in workflow_label"
                                ):
                                    Badge(STATE.workflow_label, variant="default")
                                with Else():
                                    Badge("Choose a Workflow", variant="default")

                                with If(
                                    "flow_header_text and '{{' not in flow_header_text and '$result' not in flow_header_text"
                                ):
                                    Badge(STATE.flow_header_text, variant="secondary")
                                with Else():
                                    Badge(
                                        "Choose Workflow -> Configure -> Inspect/Clarify -> Plan -> Execute",
                                        variant="secondary",
                                    )

                                with If(
                                    "workflow_guidance_text and '{{' not in workflow_guidance_text and '$result' not in workflow_guidance_text"
                                ):
                                    Muted(STATE.workflow_guidance_text)
                                with Else():
                                    Muted(
                                        "Choose whether you are attaching an existing SolidWorks file or starting a new design from scratch."
                                    )
                        with CardFooter():
                            with Row(gap=2):
                                Button(
                                    "Existing Model",
                                    variant="outline",
                                    size="sm",
                                    on_click=OpenFilePicker(
                                        accept=".sldprt,.sldasm,.slddrw",
                                        max_size=50 * 1024 * 1024,
                                        on_success=Fetch.post(
                                            f"{API_ORIGIN}/api/ui/model/connect",
                                            body={
                                                "session_id": STATE.session_id,
                                                "uploaded_files": EVENT,
                                                "feature_target_text": STATE.feature_target_text,
                                            },
                                            on_success=[
                                                *_hydrate_from_result(),
                                                ShowToast("Target model attached"),
                                            ],
                                            on_error=_error_toast(),
                                        ),
                                        on_error=_error_toast(),
                                    ),
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
                                            *_hydrate_from_result(),
                                            ShowToast("Workflow updated"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )
                                Button(
                                    "Reset",
                                    variant="outline",
                                    size="sm",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/workflow/select",
                                        body={
                                            "session_id": STATE.session_id,
                                            "workflow_mode": "unselected",
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("Workflow reset"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )

                    with If("workflow_mode == 'edit_existing'"):
                        with Card():
                            with CardHeader():
                                CardTitle("Local Model Path")
                                CardDescription(
                                    "Attach local model path and optionally target specific feature IDs such as @Boss-Extrude1."
                                )
                            with CardContent():
                                with Column(gap=2):
                                    Textarea(
                                        name="active_model_path",
                                        value=STATE.active_model_path,
                                        rows=3,
                                    )
                                    Textarea(
                                        name="feature_target_text",
                                        value=STATE.feature_target_text,
                                        rows=2,
                                    )
                                    Muted(STATE.active_model_status)
                                    Muted(STATE.feature_target_status)
                            with CardFooter():
                                Button(
                                    "Attach Local Path",
                                    variant="success",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/model/connect",
                                        body={
                                            "session_id": STATE.session_id,
                                            "model_path": STATE.active_model_path,
                                            "feature_target_text": STATE.feature_target_text,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("Target model attached"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )

                    with Card():
                        with CardHeader():
                            CardTitle("Design Spec")
                            CardDescription(
                                "Edit design intent and assumptions, then save and reclassify in one step."
                            )
                        with CardContent():
                            with Column(gap=3):
                                Textarea(
                                    name="user_goal",
                                    value=STATE.user_goal,
                                    rows=5,
                                )
                                Textarea(
                                    name="assumptions_text",
                                    value=STATE.assumptions_text,
                                    rows=4,
                                )
                        with CardFooter():
                            with Row(gap=2):
                                Button(
                                    "Save and Reclassify",
                                    variant="success",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/family/inspect",
                                        body={
                                            "session_id": STATE.session_id,
                                            "user_goal": STATE.user_goal,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast(
                                                "Design spec saved and classification refreshed"
                                            ),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )

                    with Accordion(multiple=False, collapsible=True):
                        with AccordionItem("Model Controls"):
                            with Column(gap=2):
                                Text("Assumptions")
                                Muted(
                                    "Describe manufacturing assumptions and constraints such as material, wall thickness, tolerances, and clearance targets."
                                )
                                Textarea(
                                    name="assumptions_text",
                                    value=STATE.assumptions_text,
                                    rows=4,
                                )
                                Text("Model")
                                Muted(
                                    "Choose the provider, model profile, model name, and local endpoint used for planning actions."
                                )
                                with Row(gap=2):
                                    Button(
                                        "Provider: GitHub",
                                        variant="outline",
                                        size="sm",
                                        on_click=SetState("model_provider", "github"),
                                    )
                                    Button(
                                        "Provider: Local",
                                        variant="outline",
                                        size="sm",
                                        on_click=SetState("model_provider", "local"),
                                    )
                                with Row(gap=2):
                                    Button(
                                        "Small",
                                        variant="outline",
                                        size="sm",
                                        on_click=SetState("model_profile", "small"),
                                    )
                                    Button(
                                        "Balanced",
                                        variant="outline",
                                        size="sm",
                                        on_click=SetState("model_profile", "balanced"),
                                    )
                                    Button(
                                        "Large",
                                        variant="outline",
                                        size="sm",
                                        on_click=SetState("model_profile", "large"),
                                    )
                                Textarea(
                                    name="model_name", value=STATE.model_name, rows=2
                                )
                                Textarea(
                                    name="local_endpoint",
                                    value=STATE.local_endpoint,
                                    rows=2,
                                )
                                Button(
                                    "Save Assumptions and Model Settings",
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

                        with AccordionItem("Reference Sources"):
                            with Column(gap=2):
                                Textarea(
                                    name="rag_source_path",
                                    value=STATE.rag_source_path,
                                    rows=3,
                                )
                                Text(
                                    "Use a local file path or an http/https URL for a web article, HTML page, or PDF."
                                )
                                Textarea(
                                    name="rag_namespace",
                                    value=STATE.rag_namespace,
                                    rows=2,
                                )
                                Muted(STATE.rag_status)
                                Muted(STATE.rag_provenance_text)
                                Button(
                                    "Ingest Reference Source",
                                    variant="outline",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/rag/ingest",
                                        body={
                                            "session_id": STATE.session_id,
                                            "source_path": STATE.rag_source_path,
                                            "namespace": STATE.rag_namespace,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("Reference source ingested"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )

                    with Card():
                        with CardHeader():
                            CardTitle("Planning Controls")
                            CardDescription(
                                "Refresh clarifying prompts and generate the next checkpoint plan."
                            )
                        with CardFooter():
                            with Row(gap=2):
                                Button(
                                    "Refresh Clarifying Questions",
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
                                            ShowToast("Clarification loop updated"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )
                                Button(
                                    "Plan Next Steps",
                                    variant="success",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/family/inspect",
                                        body={
                                            "session_id": STATE.session_id,
                                            "user_goal": STATE.user_goal,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("Planning checkpoint updated"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )

            with GridItem():
                with Column(gap=4):
                    with Card():
                        with CardHeader():
                            CardTitle("2. Clarification and Engineering Review")
                            CardDescription(
                                "Review questions, answer them, then confirm the recommended modeling approach before execution."
                            )

                    with Card():
                        with CardHeader():
                            CardTitle("Clarification Loop")
                            CardDescription(
                                "The model asks for missing constraints here. Enter your answer, then refresh the clarification loop."
                            )
                        with CardContent():
                            with Column(gap=2):
                                Muted(STATE.clarifying_questions_text)
                                Text("Your response to clarification prompts")
                                Textarea(
                                    name="user_clarification_answer",
                                    value=STATE.user_clarification_answer,
                                    rows=4,
                                )
                                with If("latest_error_text"):
                                    Badge(
                                        STATE.latest_error_text, variant="destructive"
                                    )
                                    with If("remediation_hint"):
                                        Muted(STATE.remediation_hint)
                        with CardFooter():
                            Button(
                                "Submit Clarification Response",
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
                                        ShowToast("Clarification response submitted"),
                                    ],
                                    on_error=_error_toast(),
                                ),
                            )

                    with Card():
                        with CardHeader():
                            CardTitle("Recommended Modeling Approach")
                            CardDescription(
                                "This replaces family-gate wording with engineering-standard review language."
                            )
                        with CardContent():
                            with Column(gap=2):
                                with Row(gap=2):
                                    Badge(STATE.proposed_family, variant="default")
                                    Badge(
                                        f"confidence: {STATE.family_confidence}",
                                        variant="secondary",
                                    )
                                Muted(STATE.family_evidence_text)
                                Muted(STATE.family_warning_text)
                        with CardFooter():
                            with Row(gap=2):
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
                                            ShowToast("Modeling approach refreshed"),
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
                                            ShowToast("Modeling approach accepted"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )

                    with Card():
                        with CardHeader():
                            CardTitle("Readiness")
                            CardDescription(
                                "Provider, adapter, preview, and DB checks before execution."
                            )
                        with CardContent():
                            with Column(gap=2):
                                with Row(gap=2):
                                    with If("readiness_provider_configured"):
                                        Badge("provider: ok", variant="success")
                                    with Else():
                                        Badge(
                                            "provider: missing", variant="destructive"
                                        )
                                    Badge(
                                        f"adapter: {STATE.readiness_adapter_mode}",
                                        variant="secondary",
                                    )
                                with Row(gap=2):
                                    with If("readiness_preview_ready"):
                                        Badge("preview: ok", variant="success")
                                    with Else():
                                        Badge(
                                            "preview: not ready", variant="destructive"
                                        )
                                    with If("readiness_db_ready"):
                                        Badge("db: ok", variant="success")
                                    with Else():
                                        Badge("db: error", variant="destructive")
                                Muted(STATE.readiness_summary)
                                Muted(STATE.active_model_status)

                    with Card():
                        with CardHeader():
                            CardTitle("Manual Review and Sync")
                        with CardContent():
                            with Column(gap=2):
                                Checkbox(
                                    label="User completed manual edits in SolidWorks",
                                    name="manual_sync_ready",
                                    value=False,
                                )
                                with If("manual_sync_ready"):
                                    Button(
                                        "Run Diff + Reconcile",
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
                                with Else():
                                    Button(
                                        "Awaiting Manual Edit Signal",
                                        variant="outline",
                                        on_click=ShowToast("No sync requested yet"),
                                    )
                                Muted(STATE.latest_message)

                    with Card():
                        with CardHeader():
                            CardTitle("Context Window")
                        with CardContent():
                            with Column(gap=2):
                                with Row(css_class="justify-between", align="center"):
                                    Text(f"{ctx_pct}% used")
                                    Muted(STATE.context_text)
                                Progress(value=ctx_pct, max=100, variant=ctx_variant)
                                Muted(
                                    "Auto-trim enabled: summarize low-priority traces first"
                                )

            with GridItem():
                with Column(gap=4):
                    with Card():
                        with CardHeader():
                            CardTitle("3. Model Output")
                            CardDescription(
                                "This lane reflects normalized brief, plan, evidence, and viewport updates after each action."
                            )
                        with CardContent():
                            with Column(gap=2):
                                Text("Latest backend status")
                                Muted(STATE.latest_message)
                                Text("Latest action")
                                Muted(STATE.latest_tool)
                                with If("mocked_tools_text"):
                                    Badge(
                                        STATE.mocked_tools_text, variant="destructive"
                                    )

                    with Card():
                        with CardHeader():
                            CardTitle("Normalized Brief")
                        with CardContent():
                            Muted(STATE.normalized_brief)

                    with Card():
                        with CardHeader():
                            CardTitle("Checkpoint Plan")
                            CardDescription(
                                "Review the current execution plan before running the next checkpoint."
                            )
                        with CardContent():
                            with Column(gap=1):
                                with If("structured_rendering_enabled"):
                                    DataTable(
                                        columns=[
                                            DataTableColumn(key="step", header="Step"),
                                            DataTableColumn(key="goal", header="Goal"),
                                            DataTableColumn(
                                                key="tools", header="Tools"
                                            ),
                                            DataTableColumn(
                                                key="status", header="Status"
                                            ),
                                        ],
                                        rows=Rx("checkpoints"),
                                        paginated=False,
                                    )
                                with Else():
                                    Muted(STATE.checkpoints_text)
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
                            CardTitle("Evidence and Retrieval Output")
                        with CardContent():
                            with Column(gap=2):
                                with If("structured_rendering_enabled"):
                                    DataTable(
                                        columns=[
                                            DataTableColumn(
                                                key="source", header="Source"
                                            ),
                                            DataTableColumn(
                                                key="detail", header="Detail"
                                            ),
                                            DataTableColumn(
                                                key="score", header="Score"
                                            ),
                                        ],
                                        rows=Rx("evidence_rows"),
                                        paginated=False,
                                    )
                                with Else():
                                    Muted(STATE.evidence_rows_text)

                    with Card():
                        with CardHeader():
                            CardTitle("3D Model View")
                            CardDescription(
                                "Live embedded 3D viewer uses STL export; PNG preview remains as fallback validation."
                            )
                        with CardContent():
                            with Column(gap=3):
                                with If(
                                    "preview_viewer_url and '/api/ui/viewer/' in preview_viewer_url and '{{' not in preview_viewer_url and '$result' not in preview_viewer_url"
                                ):
                                    Embed(
                                        url=STATE.preview_viewer_url,
                                        width="100%",
                                        height="480px",
                                    )
                                with Else():
                                    with If("preview_url"):
                                        Image(
                                            src=Rx("preview_url"),
                                            alt=Rx("preview_status"),
                                            width="100%",
                                            height="480px",
                                            css_class="border-2 border-slate-300 rounded",
                                        )
                                    with Else():
                                        Muted(
                                            "No preview captured yet. Attach a local model path, make sure SolidWorks can open it, then refresh the viewer."
                                        )
                                Muted(
                                    f"View: {STATE.preview_orientation} | Status: {STATE.preview_status}"
                                )
                        with CardFooter():
                            with Row(gap=2):
                                Button(
                                    "Refresh 3D View",
                                    on_click=Fetch.post(
                                        f"{API_ORIGIN}/api/ui/preview/refresh",
                                        body={
                                            "session_id": STATE.session_id,
                                            "orientation": STATE.preview_orientation,
                                        },
                                        on_success=[
                                            *_hydrate_from_result(),
                                            ShowToast("3D view refreshed"),
                                        ],
                                        on_error=_error_toast(),
                                    ),
                                )
                                Button(
                                    "Isometric",
                                    variant="outline",
                                    size="sm",
                                    on_click=SetState(
                                        "preview_orientation", "isometric"
                                    ),
                                )
                                Button(
                                    "Front",
                                    variant="outline",
                                    size="sm",
                                    on_click=SetState("preview_orientation", "front"),
                                )
                                Button(
                                    "Top",
                                    variant="outline",
                                    size="sm",
                                    on_click=SetState("preview_orientation", "top"),
                                )
                                Button(
                                    "Current",
                                    variant="outline",
                                    size="sm",
                                    on_click=SetState("preview_orientation", "current"),
                                )
