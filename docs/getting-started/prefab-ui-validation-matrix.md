# Prefab UI Validation Matrix (Button + Component Accounting)

Use this as the active reliability checklist while refactoring one slice at a time.

## Scope

- UI host: `http://127.0.0.1:5175/`
- API host: `http://127.0.0.1:8766/`
- Session baseline: `prefab-dashboard` (or explicit test session)

## Current execution policy

- Keep stable controls enabled.
- Keep experimental orchestration controls hidden by default.
- Fail loudly for missing model context instead of silently using wrong active SolidWorks windows.

## Validation matrix

| Area | Control / Component | Expected behavior | Current status | Notes / next action |
|---|---|---|---|---|
| Top bar | Save Context | Writes context JSON snapshot | PASS | Verify with distinct context name per run |
| Top bar | Load Context | Hydrates state from saved snapshot | PASS | Validate with both default and explicit path |
| Top bar | GO orchestration card | Hidden by default unless experimental flag enabled | PASS | Keep hidden until clarify/inspect/checkpoint reliability improves |
| Workflow | New Design | Sets workflow mode and resets planning state | PASS | Confirm state reset does not clear attached model path unexpectedly |
| Workflow | Attach Local Path | Opens target model, inspects feature tree, triggers preview | PASS | Primary stable path |
| Planning | Approve Brief | Persists normalized design goal | PASS | Required before planning actions |
| Planning | Save Preferences | Persists provider/profile/model/endpoint/assumptions | PASS | Local Gemma profile should survive context reload |
| Local model | Auto-Detect Local Model | Detects Ollama endpoint and recommended model | PASS | Requires running local Ollama service |
| Local model | Pull Recommended Model | Starts model pull workflow | PARTIAL | Validate progress/timeout UX messaging |
| LLM | Refresh Clarifications | Updates clarifications and normalized brief | PARTIAL | Depends on provider health and credentials |
| LLM | Inspect More | Updates family classification/evidence/checkpoints | PARTIAL | Depends on provider health and active model context |
| Review | Accept Family | Persists accepted family | PASS | Should stay available even if orchestration is hidden |
| Review | Manual Sync controls | Toggle/clear manual edit status | PASS | Validate reconcile flow after manual model edits |
| Output | Execute Next Checkpoint | Executes next tool step and logs result | PARTIAL | Some tools are still mocked or adapter-limited |
| Output | Evidence table | Displays source/rationale/score rows | PASS | Verify stale rows are replaced or versioned clearly |
| Preview | Refresh 3D | Reopens attached model and exports PNG/GLB/STL | PASS | Now guarded against missing `active_model_path` |
| Preview | Orientation buttons | Export correct orientation thumbnails | PASS | Verify model-specific capture, not arbitrary active window |
| Preview | 3D viewer (GLB/STL) | Loads exported geometry | PASS | Fallback to STL if GLB unavailable |
| Feature table | Row click select | Attempts feature selection in SolidWorks and updates status | PASS | Some rows may track-only when direct selection is unavailable |
| Docs context | Refresh Docs Context | Pulls filtered docs snippet | PASS | Keep query text short for relevance |
| Notes | Save Notes | Persists operator notes to session metadata | PASS | Confirm notes survive context save/load |

## Hard fail conditions (must block release)

- Preview export captures the wrong model because attached model path is missing.
- Attach model succeeds but feature tree table remains empty without visible remediation.
- Button click produces no state change, no toast, and no error message.

## Refactor sequence (one slice at a time)

1. Preview/model path integrity (completed in current slice).
2. Checkpoint execution strategy registry (replace large tool dispatch branching).
3. Clarify/Inspect reliability and credential UX.
4. Optional MCP bridge reconciliation for Prefab host deployment mode.

## Local Gemma baseline for this project

- Provider: `local`
- Profile: `small` or `balanced`
- Model name: `local:gemma4:e2b` (or detected equivalent)
- Endpoint: `http://127.0.0.1:11434/v1`
