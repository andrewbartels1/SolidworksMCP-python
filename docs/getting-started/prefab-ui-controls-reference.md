# Prefab UI Controls Reference

This reference maps every visible dashboard control in `src/solidworks_mcp/ui/prefab_dashboard.py` to state keys, backend endpoints, and expected visual changes.

Use this with:

- `docs/getting-started/prefab-ui-dashboard.md` for onboarding flow
- `http://127.0.0.1:8766/docs` for request/response schemas

## Why `prefab-dashboard` exists

- `session_id` defaults to `prefab-dashboard`.
- It is the persistent key for one dashboard session in SQLite and metadata.
- If you run one dashboard tab locally, this default is usually what you want.
- If you need isolated runs, use different session ids (currently backend/API supports this directly; there is no dedicated session-id textbox in the UI).

## Why context name and context file path exist

- **Context name** is a short token used to create a snapshot filename under `.solidworks_mcp/ui_context/`.
  - Example: `prefab-dashboard` -> `.solidworks_mcp/ui_context/prefab-dashboard.json`
- **Context file path** is an explicit path used by **Load Context**.
  - Leave empty to load the default session snapshot path.
  - Use explicit path when loading another saved snapshot.

## Top bar controls

| UI control | Type | State key(s) | Endpoint/service | Expected visual change | Notes |
| --- | --- | --- | --- | --- | --- |
| Context name | Textarea | `context_name_input` | used by `save_session_context()` | value changes in textbox | Filename token, not a model name |
| Save Context | Button | `context_save_status`, `context_file_input` | `POST /api/ui/context/save` -> `save_session_context()` | toast + status text update | Writes JSON snapshot to `.solidworks_mcp/ui_context/` |
| Context file path | Textarea | `context_file_input` | used by `load_session_context()` | value changes in textbox | Absolute or relative path to context JSON |
| Load Context | Button | many hydrated state fields | `POST /api/ui/context/load` -> `load_session_context()` | toast + status text update across cards | Loads subset of persisted fields into metadata/session |
| GO | Button | many hydrated state fields | `POST /api/ui/orchestrate/go` -> `run_go_orchestration()` | toast + orchestration status + card updates | Runs brief update + preferences + clarify + inspect in one pass |

## Lane 1 controls: workflow + settings

| UI control | Type | State key(s) | Endpoint/service | Expected visual change | Notes |
| --- | --- | --- | --- | --- | --- |
| Model path | Textarea | `model_path_input_edit` | used by model open/connect calls | value changes in textbox | Absolute path preferred |
| Feature targets | Textarea | `feature_target_text` | passed to model open/connect | value changes + feature status text | Comma/newline list like `@Boss-Extrude1` |
| Existing Model | Button + file picker | `uploaded_file_payloads` | `POST /api/ui/model/open` then `POST /api/ui/model/connect` | toast + workflow/status/preview updates | Browser upload flow for model files |
| Attach Local Path | Button | `active_model_path`, `workflow_mode` | `POST /api/ui/model/open` then `POST /api/ui/model/connect` | toast + workflow/status/preview updates | Path-based attach flow |
| New Design | Button | `workflow_mode` | `POST /api/ui/workflow/select` -> `select_workflow_mode()` | mode/workflow badges update | Switches planner copy to new-design mode |
| User goal | Textarea | `user_goal` | consumed by multiple actions | value changes in textbox | Primary design intent |
| Assumptions | Textarea | `assumptions_text` | `POST /api/ui/preferences/update` | value changes in textbox | Keep at least 5 chars to satisfy schema validation |
| Provider: GitHub | Button | `model_provider` | local UI state, persisted by save preferences | provider badge updates immediately | No HTTP call by itself |
| Provider: Local | Button | `model_provider` | local UI state, persisted by save preferences | provider badge updates immediately | No HTTP call by itself |
| Profile: Small/Balanced/Large | Buttons | `model_profile` | local UI state, persisted by save preferences | profile badge updates immediately | No HTTP call by itself |
| Model name | Textarea | `model_name` | `POST /api/ui/preferences/update` | value changes in textbox | Provider-qualified names are safest |
| Local endpoint | Textarea | `local_endpoint` | `POST /api/ui/preferences/update` | value changes in textbox | OpenAI-compatible local endpoint |
| Approve Brief | Button | `normalized_brief`, `latest_message` | `POST /api/ui/brief/approve` -> `approve_design_brief()` | toast + latest message | Explicitly commits goal as accepted brief |
| Save Preferences | Button | model/provider fields | `POST /api/ui/preferences/update` -> `update_ui_preferences()` | toast + latest message | Persists provider/profile/model/assumptions |
| Plan Next Steps | Button | family/checkpoints fields | `POST /api/ui/family/inspect` -> `inspect_family()` | toast + family/checkpoint updates | Produces/refreshes family and checkpoint plan |

## Lane 2 controls: review and acceptance

| UI control | Type | State key(s) | Endpoint/service | Expected visual change | Notes |
| --- | --- | --- | --- | --- | --- |
| Clarification answer | Textarea | `user_clarification_answer` | used by clarify/go | value changes in textbox | User response to clarifying prompts |
| Refresh Clarifications | Button | clarification fields | `POST /api/ui/clarify` -> `request_clarifications()` | toast + clarifying text + latest message/error | Needs valid model routing/auth |
| Inspect More | Button | family/checkpoint fields | `POST /api/ui/family/inspect` -> `inspect_family()` | toast + family/evidence/checkpoint updates | Needs valid model routing/auth |
| Accept Approach | Button | `accepted_family` | `POST /api/ui/family/accept` -> `accept_family_choice()` | toast + latest message | Accepts current `proposed_family` |
| Mark Manual Edits Complete / Clear Manual-Edit Flag | Buttons | `manual_sync_ready` | local UI state only | readiness badge and reconcile button visibility change | Replaces checkbox with explicit toggles |
| Run Diff and Reconcile | Button | `latest_message` | `POST /api/ui/manual-sync/reconcile` -> `reconcile_manual_edits()` | toast + message update | Compares latest snapshots |

## Lane 3 controls: execution and evidence

| UI control | Type | State key(s) | Endpoint/service | Expected visual change | Notes |
| --- | --- | --- | --- | --- | --- |
| Execute Next Checkpoint | Button | checkpoint rows, latest message | `POST /api/ui/checkpoints/execute-next` -> `execute_next_checkpoint()` | toast + checkpoint status updates | Some tools may be marked `MOCKED` |

## Viewer and feature controls

| UI control | Type | State key(s) | Endpoint/service | Expected visual change | Notes |
| --- | --- | --- | --- | --- | --- |
| Refresh 3D | Button | preview urls/status | `POST /api/ui/preview/refresh` -> `refresh_preview()` | image/viewer/status updates + toast | Also refreshes multi-view thumbnails |
| Isometric/Front/Top/Right/Current | Buttons | `preview_orientation` | `POST /api/ui/preview/refresh` | orientation/status updates + toast | Captures selected camera view |
| Feature table row click | DataTable row action | `selected_feature_name` | `POST /api/ui/feature/select` -> `highlight_feature()` then preview refresh | selected label + preview update + toast | Highlight uses adapter selection strategies |

## Bottom controls: docs and notes

| UI control | Type | State key(s) | Endpoint/service | Expected visual change | Notes |
| --- | --- | --- | --- | --- | --- |
| Docs query | Textarea | `docs_query` | used by docs refresh | value changes in textbox | Query hint for `/docs` content filtering |
| Refresh Docs Context | Button | `docs_context_text` | `POST /api/ui/docs/context` -> `fetch_docs_context()` | toast + docs text update | Pulls filtered snippet from local docs endpoint |
| Engineering notes | Textarea | `notes_text` | used by notes update | value changes in textbox | Session notes |
| Save Notes | Button | `notes_text` | `POST /api/ui/notes/update` -> `update_session_notes()` | toast + latest message | Persists notes in session metadata |

## Operator trace controls

| UI control | Type | State key(s) | Endpoint/service | Expected visual change | Notes |
| --- | --- | --- | --- | --- | --- |
| Canonical Prompt and Steering | Accordion + textarea | `canonical_prompt_text` | hydrated from `build_dashboard_state()` | textarea content updates | Read-only operator visibility |
| Recent MCP Activity | Accordion + textarea | `tool_history_text` | hydrated from `build_dashboard_state()` | textarea content updates | Read-only tool-call trace |

## Implemented but not currently surfaced in this dashboard

These backend routes exist but have no direct button in the current Prefab UI:

- `POST /api/ui/rag/ingest` (retrieval source ingestion)
- `GET /api/ui/debug/session` (full debug payload)
- `POST /api/ui/local-model/pull` (pull Ollama model)
- `POST /api/ui/local-model/query` (manual local LLM query)

## Expected controlled failure behavior

Some actions are correctly "working" even when they report an error outcome:

- `clarify`/`inspect` can return a valid response payload with a routing/auth failure message when provider credentials or model endpoint are unavailable.
- `execute-next` can return success-shaped payload with checkpoint tool failures or `MOCKED` tool notes.
- These are visible in `latest_message`, `latest_error_text`, and toast notifications so the button is not a no-op.

## Quick verification checklist

1. Click each provider/profile toggle and confirm badge text changes.
2. Edit each textarea and confirm value persists long enough to submit.
3. Trigger each action button and confirm at least one visible change: toast, badge, table, preview, or status text.
4. Confirm no literal template placeholders (for example `{{ $result... }}`) appear in textareas.
5. Confirm context save/load writes and rehydrates `.solidworks_mcp/ui_context/*.json`.
