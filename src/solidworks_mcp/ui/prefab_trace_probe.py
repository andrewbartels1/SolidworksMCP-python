"""Minimal Prefab probe app for tracing the UI startup and model-connect flow."""

from __future__ import annotations

import os

from prefab_ui import PrefabApp
from prefab_ui.actions import Fetch, OpenFilePicker, SetState, ShowToast
from prefab_ui.components import (
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
    Else,
    Embed,
    Grid,
    GridItem,
    If,
    Image,
    Muted,
    Row,
    Text,
    Textarea,
)
from prefab_ui.rx import ERROR, EVENT, RESULT, STATE

API_ORIGIN = os.getenv("SOLIDWORKS_UI_API_ORIGIN", "http://127.0.0.1:8766")
SESSION_ID_EXPR = "{{ session_id || 'prefab-dashboard' }}"
DEFAULT_ASSUMPTIONS = "Assume PETG, 0.4mm nozzle, 0.2mm layers, and 0.30mm mating clearance unless overridden."


def _result_state(_key: str, fallback: str = "") -> str:
    """Build internal result state.

    Args:
        _key (str): The key value.
        fallback (str): The fallback value. Defaults to "".

    Returns:
        str: The resulting text value.
    """

    return fallback


def _trace_error(step: str) -> list[object]:
    """Build internal trace error.

    Args:
        step (str): The step value.

    Returns:
        list[object]: A list containing the resulting items.
    """

    return [
        SetState("last_error", f"{step}: {ERROR}"),
        ShowToast(f"{step}: {ERROR}", variant="error"),
    ]


def _hydrate_trace() -> list[object]:
    """Build internal hydrate trace.

    Returns:
        list[object]: A list containing the resulting items.
    """

    return [
        SetState("trace_payload", RESULT),
        SetState("last_error", ""),
    ]


def _hydrate_preview_from_result() -> list[object]:
    """Update preview-relevant trace_payload fields directly from preview/refresh POST result.

    Avoids nested Fetch-in-on_success which is unreliable in prefab_ui 0.19.x. The POST to
    /api/ui/preview/refresh returns build_dashboard_state() whose top-level keys map 1:1 to
    trace_payload.state fields.

    Returns:
        list[object]: A list containing the resulting items.
    """
    return [
        SetState("trace_payload.state", RESULT),
        SetState("trace_payload.latest_message", RESULT.latest_message),
        SetState("trace_payload.latest_error_text", RESULT.latest_error_text),
        SetState("last_error", ""),
    ]


def _refresh_preview() -> Fetch:
    """Single preview refresh that chains _refresh_trace() on completion.

    Chaining ensures the trace payload (which contains preview_view_urls) is re-fetched
    *after* all 4 orientation PNGs have been written, not in parallel with the preview
    export.  We intentionally skip the intermediate _hydrate_preview_from_result() call
    here: the deep-path SetState it performs replaces trace_payload.state with the
    preview/refresh result which may have stale or empty preview_view_urls if called before
    the orientation PNGs are stored in metadata.  _refresh_trace() (GET
    /api/ui/debug/session) is the single source of truth — it runs after the export
    completes and returns the full trace payload including the correct preview_view_urls.

    Returns:
        Fetch: The result produced by the operation.
    """
    return Fetch.post(
        f"{API_ORIGIN}/api/ui/preview/refresh",
        body={"session_id": SESSION_ID_EXPR, "orientation": "isometric"},
        on_success=_refresh_trace(),
        on_error=_trace_error("preview refresh"),
    )


def _refresh_trace() -> Fetch:
    """Build internal refresh trace.

    Returns:
        Fetch: The result produced by the operation.
    """

    return Fetch.get(
        f"{API_ORIGIN}/api/ui/debug/session",
        params={"session_id": SESSION_ID_EXPR},
        on_success=_hydrate_trace(),
        on_error=_trace_error("debug trace fetch"),
    )


def _run_checklist() -> Fetch:
    """Build internal run checklist.

    Returns:
        Fetch: The result produced by the operation.
    """

    return Fetch.get(
        f"{API_ORIGIN}/api/health",
        on_success=[
            SetState("health_response", RESULT),
            Fetch.get(
                f"{API_ORIGIN}/api/ui/debug/session",
                params={"session_id": SESSION_ID_EXPR},
                on_success=[
                    *_hydrate_trace(),
                    Fetch.post(
                        f"{API_ORIGIN}/api/ui/workflow/select",
                        body={
                            "session_id": SESSION_ID_EXPR,
                            "workflow_mode": "edit_existing",
                        },
                        on_success=[
                            SetState("last_action", "run-checklist"),
                            SetState("checklist_result", "Checklist run completed."),
                            _refresh_trace(),
                            ShowToast(
                                "Checklist run completed. Check the UI log file for the request chain.",
                                variant="success",
                            ),
                        ],
                        on_error=[
                            SetState(
                                "checklist_result",
                                "Checklist failed at step 3 (workflow select).",
                            ),
                            *_trace_error("checklist workflow select"),
                        ],
                    ),
                ],
                on_error=[
                    SetState(
                        "checklist_result",
                        "Checklist failed at step 2 (trace snapshot).",
                    ),
                    *_trace_error("checklist trace snapshot"),
                ],
            ),
        ],
        on_error=[
            SetState("checklist_result", "Checklist failed at step 1 (health)."),
            *_trace_error("checklist health"),
        ],
    )


def _reset_probe_session() -> Fetch:
    """Build internal reset probe session.

    Returns:
        Fetch: The result produced by the operation.
    """

    return Fetch.post(
        f"{API_ORIGIN}/api/ui/workflow/select",
        body={
            "session_id": SESSION_ID_EXPR,
            "workflow_mode": "unselected",
        },
        on_success=[
            SetState("last_action", "reset-session"),
            SetState("feature_target_text", ""),
            SetState("last_error", ""),
            SetState("checklist_result", "Session reset completed."),
            _refresh_trace(),
            ShowToast("Session reset completed.", variant="success"),
        ],
        on_error=[
            SetState("checklist_result", "Session reset failed."),
            *_trace_error("reset session"),
        ],
    )


with PrefabApp(
    title="SolidWorks UI Trace Probe",
    state={
        "session_id": "prefab-dashboard",
        "feature_target_text": "",
        "model_path_input": "",
        "assumptions_text": DEFAULT_ASSUMPTIONS,
        "health_response": {"status": "pending"},
        "trace_payload": {
            "workflow_mode": "unselected",
            "latest_message": "booting...",
            "latest_error_text": "",
            "debug_summary": "loading trace...",
            "session_row_text": "{}",
            "metadata_text": "{}",
            "state_text": "{}",
            "tool_records_text": "[]",
            "state": {
                "active_model_path": "",
                "active_model_status": "No active model connected yet.",
                "preview_status": "No preview captured yet.",
                "preview_viewer_url": "",
            },
        },
        "last_action": "mount",
        "last_error": "",
        "last_picker_event": "",
        "checklist_result": "Not run yet.",
    },
    connect_domains=[API_ORIGIN],
    on_mount=[
        Fetch.get(
            f"{API_ORIGIN}/api/health",
            on_success=SetState("health_response", RESULT),
            on_error=_trace_error("health check"),
        ),
        _refresh_trace(),
    ],
) as app:
    with Column(gap=4):
        with Card():
            with CardHeader():
                CardTitle("UI Trace Probe")
            with CardContent():
                with Column(gap=2):
                    with Row(gap=2):
                        Badge(
                            "{{ trace_payload.workflow_mode || 'unselected' }}",
                            variant="default",
                        )
                        Badge(
                            "health: {{ health_response.status || 'unknown' }}",
                            variant="secondary",
                        )
                    Muted(
                        "Use this probe to verify mount, workflow selection, and model attach separately before merging changes back into the main dashboard."
                    )
                    with If("trace_payload.workflow_mode == 'unselected'"):
                        with Grid(columns={"default": 1, "lg": 2}, gap=3):
                            with Card():
                                with CardHeader():
                                    CardTitle("Edit Existing Part or Assembly")
                                    CardDescription(
                                        "Attach an existing local SolidWorks file and continue with trace-first UI behaviors."
                                    )
                                with CardFooter():
                                    with Row(gap=2):
                                        Button(
                                            "Choose Existing Workflow",
                                            variant="success",
                                            on_click=Fetch.post(
                                                f"{API_ORIGIN}/api/ui/workflow/select",
                                                body={
                                                    "session_id": SESSION_ID_EXPR,
                                                    "workflow_mode": "edit_existing",
                                                },
                                                on_success=[
                                                    SetState(
                                                        "last_action", "select-existing"
                                                    ),
                                                    _refresh_trace(),
                                                    ShowToast(
                                                        "Existing-model workflow selected"
                                                    ),
                                                ],
                                                on_error=_trace_error(
                                                    "select existing workflow"
                                                ),
                                            ),
                                        )
                                        Button(
                                            "Attach Local Model",
                                            variant="outline",
                                            on_click=OpenFilePicker(
                                                accept=".sldprt,.sldasm,.slddrw",
                                                max_size=500 * 1024 * 1024,
                                                on_success=[
                                                    SetState(
                                                        "last_picker_event", EVENT
                                                    ),
                                                    Fetch.post(
                                                        f"{API_ORIGIN}/api/ui/model/connect",
                                                        body={
                                                            "session_id": SESSION_ID_EXPR,
                                                            "uploaded_files": STATE.last_picker_event,
                                                            "feature_target_text": STATE.feature_target_text,
                                                        },
                                                        on_success=[
                                                            SetState(
                                                                "last_action",
                                                                "attach-local-model",
                                                            ),
                                                            _refresh_trace(),
                                                            ShowToast(
                                                                "Target model attached"
                                                            ),
                                                        ],
                                                        on_error=_trace_error(
                                                            "attach local model"
                                                        ),
                                                    ),
                                                ],
                                                on_error=[
                                                    SetState(
                                                        "checklist_result",
                                                        "File picker failed before upload. Check size/type and browser permissions.",
                                                    ),
                                                    *_trace_error("open file picker"),
                                                ],
                                            ),
                                        )

                            with Card():
                                with CardHeader():
                                    CardTitle("Start New Design")
                                    CardDescription(
                                        "Begin from requirements with no source model, then classify and plan checkpoints."
                                    )
                                with CardFooter():
                                    Button(
                                        "Choose New Workflow",
                                        variant="success",
                                        on_click=Fetch.post(
                                            f"{API_ORIGIN}/api/ui/workflow/select",
                                            body={
                                                "session_id": SESSION_ID_EXPR,
                                                "workflow_mode": "new_design",
                                            },
                                            on_success=[
                                                SetState("last_action", "select-new"),
                                                _refresh_trace(),
                                                ShowToast(
                                                    "New-design workflow selected"
                                                ),
                                            ],
                                            on_error=_trace_error(
                                                "select new workflow"
                                            ),
                                        ),
                                    )
                    Text("Latest message")
                    Muted("{{ trace_payload.latest_message || 'Ready.' }}")
                    Muted(
                        "Run the checklist below in order; each step should move from WAIT to PASS."
                    )
                    with Row(gap=2):
                        Button(
                            "Run Checklist",
                            variant="success",
                            on_click=[
                                SetState("checklist_result", "Running checklist..."),
                                _run_checklist(),
                            ],
                        )
                        Button(
                            "Clear/Reset Session",
                            variant="outline",
                            on_click=[
                                SetState("checklist_result", "Resetting session..."),
                                _reset_probe_session(),
                            ],
                        )
                        Button(
                            "Refresh Trace",
                            variant="outline",
                            on_click=[
                                SetState("last_action", "refresh-trace"),
                                _refresh_trace(),
                            ],
                        )
                        Button(
                            "Select Existing Workflow",
                            variant="outline",
                            on_click=Fetch.post(
                                f"{API_ORIGIN}/api/ui/workflow/select",
                                body={
                                    "session_id": SESSION_ID_EXPR,
                                    "workflow_mode": "edit_existing",
                                },
                                on_success=[
                                    SetState("last_action", "select-existing"),
                                    _refresh_trace(),
                                ],
                                on_error=_trace_error("select existing workflow"),
                            ),
                        )
                        Button(
                            "Select New Workflow",
                            variant="outline",
                            on_click=Fetch.post(
                                f"{API_ORIGIN}/api/ui/workflow/select",
                                body={
                                    "session_id": SESSION_ID_EXPR,
                                    "workflow_mode": "new_design",
                                },
                                on_success=[
                                    SetState("last_action", "select-new"),
                                    _refresh_trace(),
                                ],
                                on_error=_trace_error("select new workflow"),
                            ),
                        )
                    Textarea(
                        name="feature_target_text",
                        value=STATE.feature_target_text,
                        rows=2,
                    )
                    # --- Attach by absolute path (reliable, bypasses browser file-upload) ---
                    Textarea(
                        name="model_path_input",
                        placeholder="Paste absolute path, e.g. C:\\Parts\\part_1.sldprt",
                        value=STATE.model_path_input,
                        rows=1,
                    )
                    Button(
                        "Attach by Path",
                        variant="success",
                        on_click=[
                            SetState("last_action", "attach-by-path"),
                            Fetch.post(
                                f"{API_ORIGIN}/api/ui/model/connect",
                                body={
                                    "session_id": SESSION_ID_EXPR,
                                    "model_path": STATE.model_path_input,
                                    "feature_target_text": STATE.feature_target_text,
                                },
                                on_success=[
                                    SetState("last_action", "attached-by-path"),
                                    _refresh_trace(),
                                ],
                                on_error=_trace_error("attach by path"),
                            ),
                        ],
                    )
                    # --- Attach via browser file picker (debug: toasts EVENT on pick) ---
                    Button(
                        "Attach Local Model (file picker)",
                        variant="outline",
                        on_click=OpenFilePicker(
                            accept=".sldprt,.sldasm,.slddrw",
                            max_size=500 * 1024 * 1024,
                            on_success=[
                                SetState("last_picker_event", EVENT),
                                ShowToast(
                                    "File picker returned. Sending upload payload to backend...",
                                    variant="default",
                                ),
                                Fetch.post(
                                    f"{API_ORIGIN}/api/ui/model/connect",
                                    body={
                                        "session_id": SESSION_ID_EXPR,
                                        "uploaded_files": STATE.last_picker_event,
                                        "feature_target_text": STATE.feature_target_text,
                                    },
                                    on_success=[
                                        SetState("last_action", "attach-local-model"),
                                        _refresh_trace(),
                                    ],
                                    on_error=_trace_error("attach local model"),
                                ),
                            ],
                            on_error=[
                                SetState(
                                    "checklist_result",
                                    "File picker failed before upload. Check size/type and browser permissions.",
                                ),
                                *_trace_error("open file picker"),
                            ],
                        ),
                    )
                    with Row(gap=2):
                        Text("Last action")
                        Muted("{{ last_action || 'mount' }}")
                    with Row(gap=2):
                        Text("Inline error")
                        Muted(
                            "{{ trace_payload.latest_error_text || last_error || 'none' }}"
                        )
                    with Row(gap=2):
                        Text("Checklist result")
                        Muted("{{ checklist_result || 'Not run yet.' }}")
                    Text("Debug summary")
                    Muted("{{ trace_payload.debug_summary || 'no trace yet' }}")
                    Text("Last picker event")
                    Muted("{{ last_picker_event || '<none>' }}")

        with Card():
            with CardHeader():
                CardTitle("Step-by-Step Checklist")
            with CardContent():
                with Column(gap=2):
                    with Row(gap=2):
                        Badge(
                            "{{ health_response.status == 'ok' ? 'PASS' : 'WAIT' }}",
                            variant="secondary",
                        )
                        Text("1. Backend Health")
                    Muted("Expectation: /api/health returns status ok.")

                    with Row(gap=2):
                        Badge(
                            "{{ trace_payload.session_row_text != '{}' ? 'PASS' : 'WAIT' }}",
                            variant="secondary",
                        )
                        Text("2. Trace Snapshot")
                    Muted(
                        "Action: click Refresh Trace. Expect Session Row and Metadata cards below to populate."
                    )

                    with Row(gap=2):
                        Badge(
                            "{{ trace_payload.workflow_mode != 'unselected' ? 'PASS' : 'WAIT' }}",
                            variant="secondary",
                        )
                        Text("3. Workflow Select")
                    Muted(
                        "Action: click Select Existing Workflow or Select New Workflow. Expect workflow_mode to update."
                    )

                    with Row(gap=2):
                        Badge(
                            "{{ trace_payload.state.active_model_path ? 'PASS' : 'WAIT' }}",
                            variant="secondary",
                        )
                        Text("4. Model Attach")
                    Muted(
                        "Action: click Attach Local Model and pick a part or assembly. Expect active_model_path and active_model_status to update."
                    )

                    with Row(gap=2):
                        Badge(
                            "{{ (trace_payload.state.preview_viewer_url || trace_payload.state.preview_status == 'Static preview image ready (interactive STL unavailable).' || trace_payload.state.preview_status == 'Interactive 3D preview ready.') ? 'PASS' : 'WAIT' }}",
                            variant="secondary",
                        )
                        Text("5. Preview Pipeline")
                    Muted(
                        "Expectation: PASS only when preview_status reports image/STL readiness. Viewer URL is set only when STL exists."
                    )

                    with Row(gap=2):
                        Text("Current model path")
                        Muted("{{ trace_payload.state.active_model_path || '<none>' }}")
                    with Row(gap=2):
                        Text("Current model status")
                        Muted(
                            "{{ trace_payload.state.active_model_status || '<none>' }}"
                        )
                    with Row(gap=2):
                        Text("Current preview status")
                        Muted("{{ trace_payload.state.preview_status || '<none>' }}")

        with Card():
            with CardHeader():
                CardTitle("3D Model + View Grid")
                CardDescription(
                    "Left: interactive STL viewer. Right: orientation screenshots. Use the view buttons to refresh."
                )
            with CardContent():
                with Row(gap=3):
                    # ── Left: interactive Three.js STL viewer ──────────────
                    with Column(gap=2):
                        with If("trace_payload.state.preview_viewer_url"):
                            Embed(
                                url="{{ trace_payload.state.preview_viewer_url }}",
                                width="100%",
                                height="480px",
                            )
                        with Else():
                            Muted(
                                "Interactive STL viewer is not ready yet. Attach model and refresh trace; if only PNG export succeeded, status will say static preview image ready."
                            )
                        Muted(
                            "Viewer URL: {{ trace_payload.state.preview_viewer_url || '<none>' }}"
                        )
                        Muted(
                            "Status: {{ trace_payload.state.preview_status || 'No preview captured yet.' }}"
                        )
                    # ── Right: 2×2 orientation screenshot grid ─────────────
                    with Column(gap=2):
                        with Grid(columns=2, gap=2):
                            for _view_name, _view_label in [
                                ("isometric", "Isometric"),
                                ("front", "Front"),
                                ("top", "Top"),
                                ("right", "Right"),
                            ]:
                                with GridItem():
                                    Muted(_view_label)
                                    with If(
                                        f"trace_payload.state.preview_view_urls.{_view_name}"
                                    ):
                                        Image(
                                            src=f"{{{{ trace_payload.state.preview_view_urls.{_view_name} }}}}",
                                            alt=f"{_view_label} view",
                                            width="100%",
                                        )
                                    with Else():
                                        Muted("No screenshot yet.")
            with CardFooter():
                with Row(gap=2, wrap=True):
                    Button(
                        "Refresh Trace + Viewer",
                        variant="outline",
                        on_click=[
                            SetState("last_action", "refresh-trace-viewer"),
                            _refresh_trace(),
                        ],
                    )
                    Button(
                        "Isometric",
                        variant="outline",
                        size="sm",
                        on_click=Fetch.post(
                            f"{API_ORIGIN}/api/ui/preview/refresh",
                            body={
                                "session_id": SESSION_ID_EXPR,
                                "orientation": "isometric",
                            },
                            on_success=[
                                SetState("last_action", "view-isometric"),
                                *_hydrate_preview_from_result(),
                                ShowToast("Isometric view"),
                            ],
                            on_error=_trace_error("isometric view"),
                        ),
                    )
                    Button(
                        "Front",
                        variant="outline",
                        size="sm",
                        on_click=Fetch.post(
                            f"{API_ORIGIN}/api/ui/preview/refresh",
                            body={
                                "session_id": SESSION_ID_EXPR,
                                "orientation": "front",
                            },
                            on_success=[
                                SetState("last_action", "view-front"),
                                *_hydrate_preview_from_result(),
                                ShowToast("Front view"),
                            ],
                            on_error=_trace_error("front view"),
                        ),
                    )
                    Button(
                        "Top",
                        variant="outline",
                        size="sm",
                        on_click=Fetch.post(
                            f"{API_ORIGIN}/api/ui/preview/refresh",
                            body={
                                "session_id": SESSION_ID_EXPR,
                                "orientation": "top",
                            },
                            on_success=[
                                SetState("last_action", "view-top"),
                                *_hydrate_preview_from_result(),
                                ShowToast("Top view"),
                            ],
                            on_error=_trace_error("top view"),
                        ),
                    )
                    Button(
                        "Current",
                        variant="outline",
                        size="sm",
                        on_click=Fetch.post(
                            f"{API_ORIGIN}/api/ui/preview/refresh",
                            body={
                                "session_id": SESSION_ID_EXPR,
                                "orientation": "current",
                            },
                            on_success=[
                                SetState("last_action", "view-current"),
                                *_hydrate_preview_from_result(),
                                ShowToast("Current view captured"),
                            ],
                            on_error=_trace_error("current view"),
                        ),
                    )

        with Card():
            with CardHeader():
                CardTitle("Feature Tree")
                CardDescription(
                    "Features from the active model. Click a row to highlight it in SolidWorks."
                )
            with CardContent():
                with If(
                    "trace_payload.state.feature_tree_items && trace_payload.state.feature_tree_items.length"
                ):
                    DataTable(
                        columns=[
                            DataTableColumn(key="_selected", header=""),
                            DataTableColumn(key="name", header="Name"),
                            DataTableColumn(key="type", header="Type"),
                            DataTableColumn(key="suppressed", header="Suppressed"),
                        ],
                        rows="{{ trace_payload.state.feature_tree_items }}",
                        paginated=True,
                        on_row_click=[
                            Fetch.post(
                                f"{API_ORIGIN}/api/ui/feature/select",
                                body={
                                    "session_id": SESSION_ID_EXPR,
                                    "feature_name": "{{ $event.name }}",
                                },
                                on_success=[
                                    _refresh_preview(),
                                    ShowToast("Feature highlighted in SolidWorks"),
                                ],
                                on_error=_trace_error("feature select"),
                            )
                        ],
                    )
                    Muted(
                        "Selected: {{ trace_payload.state.selected_feature_name || 'none' }}"
                    )
                with Else():
                    Muted(
                        "No feature tree data yet. Attach a model to populate this panel."
                    )

        with Card():
            with CardHeader():
                CardTitle("Advanced Debug: Session Row")
            with CardContent():
                Textarea(
                    name="session_row_text_view",
                    value="{{ trace_payload.session_row_text || '{}' }}",
                    rows=10,
                )

        with Card():
            with CardHeader():
                CardTitle("Advanced Debug: Metadata")
            with CardContent():
                Textarea(
                    name="metadata_text_view",
                    value="{{ trace_payload.metadata_text || '{}' }}",
                    rows=14,
                )

        with Card():
            with CardHeader():
                CardTitle("Advanced Debug: Resolved UI State")
            with CardContent():
                Textarea(
                    name="state_text_view",
                    value="{{ trace_payload.state_text || '{}' }}",
                    rows=18,
                )

        with Card():
            with CardHeader():
                CardTitle("Advanced Debug: Recent Tool Records")
            with CardContent():
                Textarea(
                    name="tool_records_text_view",
                    value="{{ trace_payload.tool_records_text || '[]' }}",
                    rows=18,
                )
