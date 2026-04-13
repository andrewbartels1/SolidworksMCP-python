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
    CardHeader,
    CardTitle,
    Column,
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
    return fallback


def _trace_error(step: str) -> list[object]:
    return [
        SetState("last_error", f"{step}: {ERROR}"),
        ShowToast(f"{step}: {ERROR}", variant="error"),
    ]


def _hydrate_trace() -> list[object]:
    return [
        SetState("trace_payload", RESULT),
        SetState("last_error", ""),
    ]


def _refresh_trace() -> Fetch:
    return Fetch.get(
        f"{API_ORIGIN}/api/ui/debug/session",
        params={"session_id": SESSION_ID_EXPR},
        on_success=_hydrate_trace(),
        on_error=_trace_error("debug trace fetch"),
    )


def _run_checklist() -> Fetch:
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
                                        "uploaded_files": EVENT,
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
                CardTitle("Session Row")
            with CardContent():
                Textarea(
                    name="session_row_text_view",
                    value="{{ trace_payload.session_row_text || '{}' }}",
                    rows=10,
                )

        with Card():
            with CardHeader():
                CardTitle("Metadata")
            with CardContent():
                Textarea(
                    name="metadata_text_view",
                    value="{{ trace_payload.metadata_text || '{}' }}",
                    rows=14,
                )

        with Card():
            with CardHeader():
                CardTitle("Resolved UI State")
            with CardContent():
                Textarea(
                    name="state_text_view",
                    value="{{ trace_payload.state_text || '{}' }}",
                    rows=18,
                )

        with Card():
            with CardHeader():
                CardTitle("Recent Tool Records")
            with CardContent():
                Textarea(
                    name="tool_records_text_view",
                    value="{{ trace_payload.tool_records_text || '[]' }}",
                    rows=18,
                )
