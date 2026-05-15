# UI Refactor Assessment — server.py / service.py

**Date**: May 2026
**Status**: In progress — Phase 1 implemented

---

## 1. Current-state inventory

| File | Lines | Role |
|---|---|---|
| `ui/service.py` | compatibility shim | Legacy import surface that re-exports focused modules from `ui/services/` |
| `ui/server.py` | app assembly | FastAPI app, middleware, router mounting, logging |
| `ui/prefab_dashboard.py` | Prefab UI definition | Client-side dashboard layout and fetch wiring |
| `ui/services/*.py` | focused services | Session, model, preview, LLM, checkpoint, docs, shared utils |
| `ui/routers/*.py` | route slices | Route handlers grouped by domain |

---

## 2. What works vs what is broken

### Working ✅

- **3D preview** — GLB/STL export via Three.js embedded viewer; PNG multi-orientation captures
- **Feature tree table** — loads from snapshot, component selection highlights in SolidWorks
- **Model connect/attach** — opens `.sldprt` / `.sldasm` via COM adapter, inspects feature tree
- **Session persistence** — SQLite via `history_db`
- **Context save/load** — JSON snapshots in `.solidworks_mcp/ui_context/`
- **Engineering notes** — free-text persisted in session metadata
- **Docs context** — HTML scrape of `/docs` endpoint filtered by query term

### Broken / mocked ❌

| Component | Reason |
|---|---|
| **Clarification** (Refresh Clarifications) | Requires `GH_TOKEN` / `OPENAI_API_KEY` with models:read scope; model name routing fragile |
| **Family inspect** (Inspect More) | Same LLM dependency; also fails if no active model attached |
| **GO orchestration** | Wraps clarify + inspect; fails if either fails |
| **Checkpoint execution** (Execute Next) | `create_sketch`, `add_line`, `create_extrusion` partially wired; `check_interference` MOCKED; others MOCKED |
| **Engineering Signals** | Confidence badge depends on LLM result; always shows "unknown" |
| **Design spec / model settings** | Provider selection fragile; local model probe works but model name normalisation has edge cases |
| **MCP Bridge** | `McpError: -32601 Method not found` — Prefab renderer sends `initialize` to an MCP server that is not present in this deployment mode |
| **Plan Next Steps** | Button triggers unimplemented planning sub-flow |

### Mitigations now available (May 2026)

- Local inference path is validated with local provider settings (`local:*` model names) and Ollama endpoint routing.
- Preview refresh now enforces successful target-model reopen before image export, preventing captures from the wrong active SolidWorks document.
- Adapter export resolution now prefers the tracked `currentModel` unless `ActiveDoc` matches the same file, which fixes wrong-window preview/export captures when SolidWorks focus drifts.
- Tested operator runbook for the U-Joint sample bracket workflow:
  - `docs/getting-started/prefab-ui-u-joint-bracket-runbook.md`

### Live verification notes (May 4, 2026)

- The default dashboard now hides `Plan Next Steps` and the clarification/acceptance action card unless `SOLIDWORKS_UI_EXPERIMENTAL_ORCHESTRATION=1` is set.
- The Prefab renderer still logs `McpError: -32601 Method not found` on page load, confirming the MCP bridge remains unresolved even though Fetch-based routes work.

---

## 3. Is FastAPI the right backend?

**Yes.** The Prefab UI uses `Fetch.get/post` to call HTTP endpoints — it needs a REST server.
FastAPI is appropriate: async, type-annotated, OpenAPI docs out of the box, and already integrated.

Rejected alternatives:

- **Streamlit** — server-side re-render model does not fit the client-reactive Prefab component tree; no embedded 3D viewer support
- **Gradio** — similar limitations; geared toward ML model demos
- **FastMCP native Prefab tools** — correct long-term direction for a full MCP client, but requires a working MCP client bridge (see broken MCP Bridge above); the FastAPI layer remains necessary until the bridge is fixed

---

## 4. FastMCP Prefab / Generative UI findings

From <https://gofastmcp.com/apps/prefab> and <https://gofastmcp.com/apps/generative>:

- Prefab components (`Column`, `Row`, `Fetch`, `If`, etc.) are the **current** approach and already in use — no migration needed
- `GenerativeUI` (FastMCP ≥ 3.2.0) lets the LLM write Prefab Python code at runtime inside a Pyodide sandbox — useful for dynamic report panels but not for the CAD-control flow that requires real adapter calls
- The **MCP Bridge error** (`-32601 Method not found`) occurs because the Prefab renderer tries to call `tools/list` / `initialize` on a connected MCP server, but the current deployment has no MCP server wired into the Prefab host. This is non-fatal (the Fetch-based API calls still work) but should be resolved by either mounting the MCP server at the same host origin or disabling bridge mode in the Prefab config

---

## 5. SOLID violations in the current code

### Single Responsibility (remaining offender)

The old `service.py` monolith has been split, but the service layer as a whole still handles:

- Session CRUD and state serialisation
- LLM prompting and structured agent execution
- Adapter orchestration (open model, feature tree, preview export)
- RAG ingestion and docs scraping
- Checkpoint plan execution
- Context snapshot save/load

### Open/Closed

- Tool routing in `_run_checkpoint_tools` is a giant `if/elif` chain — adding a new tool requires modifying the function
- Model name normalisation is a chain of `if model_name.startswith(...)` checks

### Dependency Inversion

- Service functions directly call `create_adapter(load_config())` — the adapter is not injected, making unit tests require mocking at import-time
- `_build_agent_model` creates pydantic-ai model objects inline — no abstraction layer

---

## 6. Target architecture

```
ui/
  server.py           # Thin FastAPI app assembly: middleware, mount routers (~100 lines)
  service.py          # Backwards-compat re-export shim (import from services/)
  prefab_dashboard.py # UI with broken sections commented out
  schemas.py          # DashboardUIState, DashboardCheckpoint, etc. (unchanged)
  local_llm.py        # Ollama probe/pull/query (unchanged for now)
  services/
    __init__.py       # Public re-exports (all names that server.py currently imports)
    _utils.py         # Shared utilities: _sanitize_*, _parse_json_blob,
                      #   _merge_metadata, _persist_ui_action, _trace_*
    session_service.py  # Session CRUD, state assembly (build_dashboard_state)
    model_service.py    # connect_target_model, open_target_model
    preview_service.py  # refresh_preview, highlight_feature
    llm_service.py      # request_clarifications, inspect_family, run_go_orchestration
    checkpoint_service.py # execute_next_checkpoint, _run_checkpoint_tools
    docs_service.py     # fetch_docs_context, ingest_reference_source
  routers/
    __init__.py
    session.py        # GET /api/ui/state, POST /api/ui/brief/approve, etc.
    model.py          # POST /api/ui/model/connect, /model/open
    preview.py        # POST /api/ui/preview/refresh, /feature/select, /manual-sync/reconcile
    llm.py            # POST /api/ui/clarify, /family/inspect, /family/accept, /orchestrate/go
    checkpoint.py     # POST /api/ui/checkpoints/execute-next
    docs.py           # POST /api/ui/docs/context, /rag/ingest
    local_model.py    # GET/POST /api/ui/local-model/*
    viewer.py         # GET /api/ui/viewer/{session_id}
    context.py        # POST /api/ui/context/save, /context/load, /notes/update
```

---

## 7. Broken UI sections to comment out (Phase 1)

Status update (May 2026): these controls are now gated behind
`SOLIDWORKS_UI_EXPERIMENTAL_ORCHESTRATION=1` in `prefab_dashboard.py`.
Default behavior keeps them hidden so the primary attach/preview/feature workflows stay stable.

Comment out in `prefab_dashboard.py` — these sections call LLM endpoints that reliably
fail without credentials, obscure working sections, and confuse users:

| Section | Reason to disable |
|---|---|
| **Clarification & Engineering Review column** (column 2 of 3-column layout) | LLM-dependent; always shows errors |
| **GO button + GO status bar** | Wraps LLM calls; fails when clarify/inspect fail |
| **Checkpoint Plan + Execute Next** (model output column) | Mostly MOCKED; checkpoint execution not reliable |
| **Engineering Signals badges** | Confidence always "unknown" without successful LLM |
| **Plan Next Steps button** | Calls unimplemented planning sub-flow |

Keep active (working):

- Workflow selector (Edit Existing / New Design / Attach Local Path)
- Model path input + Attach button
- 3D Preview (multi-view images + Three.js viewer)
- Feature tree table + feature select
- Session notes
- Docs context
- Operator Trace (read-only)
- Context save/load

---

## 8. Implementation phases

| Phase | Scope | Risk |
|---|---|---|
| **1** (done) | Create `services/` + `routers/`, slim `server.py`, comment out broken UI | Low — backwards compat shim in `service.py` |
| **2** | Fix MCP Bridge: mount FastMCP server at same origin or configure Prefab host to not bridge | Medium |
| **3** | Wire real LLM flows with proper credential UX (env var checklist, error toasts with actionable messages) | Medium |
| **4** | Wire checkpoint execution properly: replace `if/elif` chain with a strategy registry | Low |
| **5** | Replace `on_event("startup")` (deprecated) with FastAPI lifespan context manager | Low |
