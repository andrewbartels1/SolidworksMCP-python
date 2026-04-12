# Interactive Design Foundation Tracker

Last updated: 2026-04-11

## Purpose

Track what is done vs. what still needs work for:

1. Interactive UI research (Prefab/FastMCP app direction)
2. RAG + orchestration research for stronger tool selection and planning

---

## Current Status Snapshot

| Workstream | Status | Notes |
| --- | --- | --- |
| Dedicated feature-tree reconstruction skill | Done (rough cut) | Added workspace skill file for inspect-classify-delegate routing |
| Docs migration from silhouette-first | In progress | Core plan exists; tutorial/demo pages still need updates |
| Code-backed feature-family classification helper | Done (initial) | `feature_tree_classifier` exists and is wired in tooling; needs more evals and fixtures |
| Interactive UI for guided choices | In progress | Added concrete app workflow and prompt/response patterns |
| Local memory DB for errors/remediation | Done (expanded) | Added sessions/checkpoints/tool calls/evidence/snapshots/sketch-graph persistence |
| ResearchTODO: Open CAD datasets and LMM path | In progress | Added dataset/model landscape and evaluation questions for open-source direction |

## Prefab App Component Status (2026-04-11)

| Component | Current Status | Notes |
| --- | --- | --- |
| Backend API server (FastAPI) | Working | Routes respond and `/docs` is available |
| Frontend launch (Prefab) | Working with caveats | UTF-8/console launch issues were mitigated; validate on user machine each run |
| Design Intent panel | Partially working | Goal input and brief approval wired |
| Clarifying Questions action | Partially working | Calls backend LLM path; depends on provider credentials/config |
| Strategy checkpoint card (renamed from Family Classification Gate) | Partially working | `Go: Plan Next Steps`, inspect, and accept actions wired |
| Checkpoint queue rendering | Working with guards | Structured table restored behind schema/array guards with safe text fallback |
| Evidence rendering | Working with guards | Structured table restored behind schema/array guards with safe text fallback |
| Execute next checkpoint | Partially working | Runs supported adapter tools; unsupported operations are marked mocked |
| Manual SolidWorks sync | Partially working | Reconcile endpoint exists; diff logic is currently simplified |
| 3D model preview | Partially working | PNG snapshot refresh works when export path is valid; embedded 3D viewport is mocked |
| Context window bar | Cosmetic only | Static placeholder values |
| LLM provider selection in UI | Partially working | Provider + model profile controls now persist in dashboard metadata |
| Local model dropdown (Gemma-class models) | Partially working | Local small/balanced/large defaults map to Gemma-family model names |
| Assumptions editor | Working | Dedicated editable assumptions section with persistent save action |
| Readiness panel | Working | Reports provider credentials, adapter mode, preview readiness, and DB readiness |
| Inline card-level error surface | Working | `latest_error_text` + `remediation_hint` shown in key cards |
| RAG ingestion for user-owned engineering books | Partially working | Path-based PDF/text ingestion scaffold writes a local retrieval index and provenance summary |
| Web research fallback | Missing | No constrained web-search tool integration in UI loop yet |
| Feature-tree target highlighting (`@feature-id`) | Partially working | UI now persists grounded feature-target refs and validates them against the attached model tree |
| Attached target-model workflow | Working | Users can attach a `.sldprt`/`.sldasm`, inspect it, and seed planning/preview from that model |

## Prefab App Todo Backlog (Prioritized)

### P0 — Make core loop reliable

1. Add an explicit "Plan Next Steps" primary path from Design Intent to strategy checkpoint (done).
2. Restore structured checkpoint/evidence rendering safely (done: guarded DataTable + fallback text).
3. Add a backend/UI readiness panel that reports: provider configured, SolidWorks adapter mode, preview export readiness, and DB session status (done).
4. Add robust error surfaces in UI cards (inline error + remediation hint), not only toasts (done).

### P1 — Clarify user workflow and naming

1. Keep the renamed "Modeling Strategy Checkpoint" wording and add helper text for family meaning and confidence interpretation.
2. Add a linear flow header: `Goal -> Assumptions -> Clarify -> Plan -> Execute` (done).
3. Add a dedicated assumptions editor section so users can inspect/edit accepted assumptions before planning (done).

### P2 — LLM/model controls

1. Add model/provider selector in UI state and backend request payloads (done: preferences endpoint + persisted UI state).
2. Add local-model profiles (small/medium/large) with hardware-aware defaults and warnings (partially done: profile selection and default mapping).
3. Add provider adapters for local inference endpoints (OpenAI-compatible local server first) and test with Gemma-family models where available (in progress).

CADAM-derived note:

- CADAM's parametric-control UX reinforces keeping assumptions/model controls editable at runtime. We now mirror that pattern in the dashboard and should extend it to geometry-level slider controls in P4/P5.

### P3 — RAG for user-owned technical books

1. Build a "bring-your-own-content" ingestion flow: file picker, chunking profile, embedding profile, and index namespace (partially done: path-based scaffold and local JSON index).
2. Add explicit copyright-safe mode: only index user-provided files; no bundled proprietary corpora.
3. Add retrieval provenance panel in UI for plan steps (source file/chunk/score) (partially done: session-level provenance summary).

### P4 — Research fallback and advanced interaction

1. Add constrained engineering web-research fallback (query templates + source allowlist + citation capture).
2. Add feature-tree selection handoff (`@feature-id`) from UI to planning context (partially done: persisted target refs + validation against attached model tree).
3. Add assembly mate targeting by selected component references.

### P5 — Validation and evaluation

1. Add benchmark run mode from UI session logs (Bat, U-Joint Pin, Paper Airplane, practical printable part).
2. Track metrics: classification accuracy, first-feature correctness, correction count, rollback success.

## Execution Todo Ledger (Do-Not-Lose)

This section is the durable running list for in-flight implementation work so context-window truncation does not lose requirements.

### Active now

1. Apply Pydantic-first contracts across dashboard UI/backend payloads (shared schema module, explicit field docs, validation).
1. Complete P0 reliability items: readiness panel, safe structured checkpoint/evidence rendering, and inline per-card error surfaces.
1. Keep the core interaction loop clear for users: `Design Intent -> Assumptions -> Clarify -> Plan -> Execute` and an explicit primary action button for planning.

### Requested by user and accepted into backlog

1. Use `pydantic-ai` where LLM response structures are generated/validated (clarify/inspect/planning payloads).
1. Add local model selection UX: provider dropdown, small/medium/large profile selector, and Gemma-family local endpoint integration path.
1. Add user-owned engineering-book RAG ingestion (copyright-safe BYO corpus only).
1. Add constrained engineering web research fallback with source provenance.
1. Add feature-tree targeting workflow (`@feature-id`) and assembly mate target selection.
1. Add global parameter/slider experimentation workflow for part-feature sensitivity.
1. Evaluate Python-native simple 3D rendering equivalents for frontend integration (`pyvista`, `trimesh`, `plotly` mesh viewers).
1. Test the dashboard against a how-to document and record how much retrieved guidance actually changes planning quality.
1. Document separate workflows clearly: MCP server only, UI-driven workflow, and hybrid workflow.
1. Validate the concrete saved-part path workflow using `.generated/part_1.sldprt` and a grounded target such as `@Boss-Extrude1`.

## Context Window Budget

Use a predictable budget per turn so the workflow remains stable as retrieval and tool logs grow.

- Global target: keep active prompt + retrieved evidence under 14k tokens before tool execution.
- Hard cap policy: trim low-relevance evidence once context exceeds 16k tokens.
- Orchestrator budget: 6k-8k tokens.
- Classifier + routing budget: 2k-3k tokens.
- Printability/clearance specialist budget: 2k-3k tokens each.
- Tool-call trace budget: 1k-2k tokens (summarized, never raw full logs by default).

Token allocation order:

- mandatory: current goal, accepted family, latest checkpoint, rollback pointer
- high priority: top 3-6 evidence chunks with provenance
- medium priority: prior similar failures + remediation
- low priority: older conversation turns and verbose intermediate output

When over budget:

- collapse prior turns to structured summaries
- keep only top-scoring evidence per source type
- replace raw payloads with compact key-value extracts
- defer non-critical explanation until after execution

## What Was Implemented (Items 1, 2, 3)

### 1) Dedicated reconstruction skill

- Added: `.github/skills/feature-tree-reconstruction/SKILL.md`
- Purpose: enforce inspect-classify-delegate behavior, confidence gating, and checkpoint execution.
- Includes triggers for reverse engineering, feature-tree classification, and VBA fallback routing.

### 2) Family-gated docs page and nav wiring

- Added: `docs/agents/family-gated-tool-routing.md`
- Added to docs nav under Agents and Skills in `mkdocs.yml`.
- Includes:
  - family -> allowed tool shortlist table
  - checkpoint handoff prompts
  - human-in-SolidWorks edit handback and diff workflow
  - printability handoff assumptions/outputs

### 3) SQLite schema/API expansion

- Extended `src/solidworks_mcp/agents/history_db.py` with new persistent entities:
  - `DesignSession`
  - `PlanCheckpoint`
  - `ToolCallRecord`
  - `EvidenceLink`
  - `ModelStateSnapshot`
  - `SketchGraphSnapshot`
- Added helper APIs for insert/list/update/upsert operations.
- Exported the new APIs via `src/solidworks_mcp/agents/__init__.py`.
- Added tests to `tests/test_agents_history_db.py` for new tables and APIs.

Section F implementation note:

- SketchGraphs-style relational data is now persisted in lightweight SQLite via `SketchGraphSnapshot` (`nodes_json`, `edges_json`, metadata).
- This keeps storage local and simple while still exposing graph semantics to retrieval/planning.

---

## Final Research Leg: Market + Research Signals

These are reference notes only (non-actionable by themselves), added to ground architecture decisions.

### Market/workflow signals

1. Prefab (Prefect)
    - Link: <https://github.com/PrefectHQ/prefab>
    - Takeaway: Python-declared, protocol-first UI for MCP apps; strong fit for agent-readable, interactive checkpoint UIs.

2. Onshape ecosystem trend toward AI + automation + branching workflows
    - AI/agents blog index signal: <https://www.onshape.com/en/blog>
    - Example post references from index:
       - <https://www.onshape.com/en/blog/ai-artificial-intelligence-cloud-native-cad-pdm-platform>
       - <https://www.onshape.com/en/blog/adam-ai-app-store-cad-co-pilot>
    - Takeaway: practical CAD AI workflows are converging on collaboration primitives (branch/merge/history), not one-shot generation.

### Research signals

1. SketchGraphs (constraint-graph representation)
    - Link: <https://arxiv.org/abs/2007.08506>
    - Takeaway: sketches are relational constraint graphs; retrieval should index entities + constraints, not just text.

2. DeepCAD (operation-sequence representation)
    - Link: <https://arxiv.org/abs/2105.09492>
    - Takeaway: CAD as operation sequences is a viable modeling space; supports plan/checkpoint generation grounded in feature history.

3. ReAct (interleaved reason/act loops)
    - Link: <https://arxiv.org/abs/2210.03629>
    - Takeaway: inspect/act/observe loops are better than one-shot planning for tool-rich CAD tasks.

4. RAG (evidence retrieval over latent memory)
    - Link: <https://arxiv.org/abs/2005.11401>
    - Takeaway: retrieval with provenance is critical for safe tool routing and explainable CAD planning.

## ResearchTODO: Open CAD Dataset and LMM Landscape

Goal: evaluate whether we can build an open, SolidWorks-compatible "Large Mechanical Model" style stack using open datasets, open methods, and local retrieval.

### Why this is added now

Commercial positioning (example: Leo) points to an LMM concept with multi-modal input and engineering-aware generation. We need an open-source path that remains auditable and reproducible.

Reference:

1. Leo about page: <https://www.getleo.ai/about>

### Candidate open datasets to evaluate first

- Dataset: SketchGraphs.
- Link: <https://arxiv.org/abs/2007.08506>.
- Signal: large-scale relational sketch constraints suitable for sketch-level reasoning.

- Dataset: DeepCAD dataset and sequence formulation.
- Link: <https://arxiv.org/abs/2105.09492>.
- Signal: CAD operation-sequence representation (Transformer-friendly) and public dataset claim.

- Dataset: Fusion 360 Gallery.
- Link: <https://arxiv.org/abs/2010.02392>.
- Signal: human design sequences and a programmatic reconstruction environment.

### Research questions (non-actionable for now)

- Which dataset best transfers to SolidWorks feature semantics (extrude/revolve/sheet metal/assembly)?
- How do we map dataset operation vocabularies to SolidWorks MCP tool families and VBA fallback boundaries?
- Can a hybrid model work better than one monolithic LMM?
- Candidate architecture for that hybrid: retrieval-first planner + small CAD sequence model + strict tool router.
- What is the minimum viable benchmark to compare open approach vs commercial copilots?
- Candidate benchmark metric: family classification accuracy.
- Candidate benchmark metric: first-feature correctness.
- Candidate benchmark metric: correction count before valid build.
- Candidate benchmark metric: rollback success rate after manual SolidWorks edits.

### Suggested open architecture experiments

- Retrieval-only baseline.
- Method: no fine-tuned CAD model; rely on retrieval + classifier + tool gating.

- Sequence-model augmentation.
- Method: add a lightweight CAD-sequence model for checkpoint suggestions only.

- Sketch-graph augmentation.
- Method: use stored sketch graph snapshots from SQLite as structured evidence in prompts.

- Human-edit reconciliation loop.
- Method: measure plan recovery quality after out-of-band manual SolidWorks changes.

### Data and governance checks to include in future research phase

1. Licensing and redistribution limits for each dataset.
1. PII/IP leakage risk in training examples.
1. Reproducibility of preprocessing pipelines and tokenization rules.
1. Traceability from generated plan step back to evidence chunk.

## Rough-Cut App Workflow (CAD Assistant + Orchestrator)

This is the current target behavior for an interactive assistant that works with SolidWorks.

### Phase 0: Idea capture / optional 2D-to-3D concept preview

- User enters goal and constraints (function, dimensions, material, printer profile).
- Assistant can generate a concept preview path (text + sketch concept), clearly marked provisional.
- No direct model execution until family is accepted.

### Phase 1: Inspect and classify

- If model exists, agent runs inspect tools and classifies family with confidence + evidence.
- User gets prompted to approve family or request re-inspection.

### Phase 2: Orchestrated planning

- Orchestrator generates 3-6 checkpoint plan.
- Each checkpoint has allowed tools, success criteria, and rollback target.

### Phase 3: Interactive execution and specialist sub-agents

- For each checkpoint, orchestrator calls specialists as needed:
  - printability/tolerance agent
  - clearance/fit checker
  - VBA fallback reconstructor for unsupported families
- Results are surfaced in Q/A style before execution:
  - "Here is what I found"
  - "Here are options and risks"
  - "Approve option 1/2/3 or request changes"

### Phase 4: Human SolidWorks edit handoff and diff sync

- User can pause and edit directly in SolidWorks.
- User signals completion of manual edits.
- Agent runs a diff pass against last accepted snapshot and offers reconciliation:
  - accept user edits and update remaining plan
  - patch only deltas to stay on goal
  - rollback to prior snapshot

### Phase 5: Persist and learn

- Persist session/checkpoints/tool calls/evidence/snapshots/sketch-graph records.
- Store failures with root cause/remediation and reuse in future retrieval.

## UI Composition Draft (Prefab-Style)

This composes the app directly from the rough-cut workflow so we can test behavior quickly.

### UI layout

- Panel A: goal and constraints
  - part intent
  - printer/material/nozzle/layer-height
  - required envelope and joint type
- Panel B: inspect -> classify -> checkpoints
  - family card with confidence and warnings
  - checkpoint queue with approve/reject controls
  - execution status per checkpoint
- Panel C: evidence and diffs
  - retrieved evidence list with source links
  - latest model snapshot and delta summary after manual SolidWorks edits
  - rollback target selector

### Prompt and response flow (rough cut)

- Prompt A (intent capture):
  - "Design a printable U-bracket assembly for [use case] with [constraints]."
- Assistant response A:
  - asks only missing constraints and returns a normalized design brief

- Prompt B (classification gate):
  - "Inspect current model state and classify family before any build actions."
- Assistant response B:
  - `family`, `confidence`, `evidence`, `warnings`, and first 3 checkpoints

- Prompt C (checkpoint execution):
  - "Execute checkpoint [n] with allowed tools only and report verification."
- Assistant response C:
  - tool calls, verification summary, and next checkpoint options

- Prompt D (manual edit sync):
  - "I finished edits in SolidWorks. Reconcile changes with the goal."
- Assistant response D:
  - diff summary and options:
    - accept manual edits and replan forward
    - patch to realign with goal
    - rollback to checkpoint snapshot

### Try-now path

- Step 1: install Prefab package in test environment.
  - `pip install prefab-ui`
- Step 2: validate basic component composition using the welcome-card pattern (`Card`, `Input`, `Rx`) from Prefab docs/README.
- Step 3: map the three-panel workflow above into a first internal UI prototype.
- Step 4: wire panel actions to existing persistence APIs in `history_db.py`.
- Step 5: run one end-to-end U-bracket session and capture:
  - checkpoint approvals
  - tool-call logs
  - snapshot diffs after manual SolidWorks edits

Current limitation:

- Prefab docs page extraction was partial via crawler, so local app-run command details should be confirmed against the live Prefab docs and examples when implementing the first executable UI file.

## UI Prototype Status (Implemented)

Prototype file created:

- `examples/prefab_cad_assistant/cad_assistant_dashboard.py`

What it currently demonstrates:

- Design-intent capture card and classification gate
- Checkpoint queue with allowed-tool visibility
- Context-window progress card (token budget visualization)
- Evidence/retrieval panel
- Manual SolidWorks edit sync card with diff/reconcile trigger

How to try it locally:

- Install Prefab package in the active environment: `python -m pip install prefab-ui`.
- Serve the prototype (repo-local venv): `.venv\\Scripts\\prefab.exe serve examples/prefab_cad_assistant/cad_assistant_dashboard.py`.
- Export static output (repo-local venv): `.venv\\Scripts\\prefab.exe export examples/prefab_cad_assistant/cad_assistant_dashboard.py`.

First integration wiring targets:

- Replace static checkpoint table rows with records from `PlanCheckpoint`
- Write execute/rollback actions into `ToolCallRecord` and `ModelStateSnapshot`
- Populate evidence panel from `EvidenceLink`
- On manual sync, run diff workflow and persist reconciliation decision

## 1) Research: Prefab-Like Interactive App for Prompting and Agent Guidance

## What Prefab appears to be

Based on current README/docs:

- Python-first declarative UI framework (`prefab-ui`) with prebuilt components
- Built for MCP app workflows and agent-generated interfaces
- Compiles component tree to a protocol rendered by a bundled React frontend
- Reactive state model in Python (no direct JS authoring required for many interactions)

## Fit for this repository

High fit for a guided "human-in-the-loop CAD planning" UI because we need:

- explicit user checkpoints (family classification confirmation)
- quick choice chips/cards (hinge type, joint strategy, tolerancing mode)
- evidence panes (retrieved docs, failures, feature tree snapshots)
- execution gating controls (approve step, replan, delegate to VBA path)

## Recommended UX architecture (MVP)

1. Left pane: "Intent + Constraints"

- part goal, printer profile, envelope limits, material

1. Center pane: "Inspect -> Classify -> Plan"

- feature-family card with confidence/evidence
- first 3-6 planned operations only

1. Right pane: "Evidence + Errors"

- retrieved chunks with provenance
- prior similar failures and remediations

1. Bottom action rail:

- Approve classification
- Request alternatives
- Execute next step
- Roll back to checkpoint

## Prefab POC scope (small)

- Build one app focused on a single task: "Reconstruct existing part from feature tree"
- Use mocked adapter outputs first
- UI emits strict action payloads (approve/reject/replan/delegate)
- Persist each decision and correction into `DesignIntentSession`

## Risks

- New UI stack adds maintenance overhead
- Agent-generated UI still needs strict schema checks to avoid malformed controls
- Should not bypass existing docs-first workflows; must be additive and optional

---

## 3) Research: RAG + Orchestration for CAD Idea -> Plan -> Build

## Problem to solve

Tool count is high and LLMs degrade when selecting among many tools without tight context/routing. We need constrained retrieval and explicit delegation boundaries.

## Recommended architecture (practical)

### A. Orchestrator-first flow

1. Observe state (model/image/doc)
2. Classify feature family
3. Retrieve bounded evidence set
4. Produce short checkpoint plan
5. Request human approval at boundaries
6. Execute next checkpoint only
7. Verify and log outcomes

### B. Retrieval tiers and storage

1. Structured evidence (highest priority)

- feature tree snapshots
- mass properties
- tool call traces + normalized params
- error records with root cause + remediation

1. Semi-structured docs

- local how-tos, worked examples, tool-catalog pages

1. External/tutorial corpus

- transcript chunks with operation/family tags

### C. Suggested SQLite schema expansion (incremental)

- `design_sessions`
  - id, objective, accepted_family, status, created_at, updated_at
- `plan_checkpoints`
  - session_id, step_index, planned_action, approved_by_user, executed, result
- `tool_calls`
  - session_id, checkpoint_id, tool_name, input_json, output_json, success, latency_ms
- `failures`
  - session_id, tool_call_id, error_type, root_cause, remediation, recovered
- `evidence_links`
  - session_id, checkpoint_id, source_type, source_id, relevance_score, rationale

### D. Retrieval strategy

Hybrid retrieval with explicit filters:

1. lexical exact-match for API/tool names
2. embeddings for conceptual similarity
3. metadata filtering by feature family + document type
4. failure-memory retrieval keyed by tool and error class

### E. Tool overload mitigation

- Family-gated tool shortlist per step (do not expose all tools at once)
- Confidence thresholds that force additional inspect steps
- Delegate unsupported families (sheet metal/surface-heavy) to VBA-aware reconstructor
- Prefer checkpoint plans of 3-6 steps over monolithic 20-step plans

### F. SketchGraphs-informed direction

Treat sketches/features as relational structures, not only text/image:

- index entities + constraints + parent-child links
- store sketch completeness flags (under-constrained, unresolved references)
- retrieve prior sketch patterns when proposing first feature

---

## U-Bracket Assembly Demo Path (Target End-to-End Example)

Use this as the benchmark narrative for prompting and UX.

### Goal

Prompt from idea to a robust U-bracket assembly plan with inspectable evidence and minimal rework.

### Recommended prompt flow

1. User intent prompt

- "Design a printable U-bracket assembly with a pin joint, sized for [load/use], printer [model/build volume], material [PLA/PETG/etc]."

1. Orchestrator asks for missing constraints

- clearances, screw standard, wall thickness target, max envelope

1. Classification/planning prompt

- identify if single-part bracket vs multi-part assembly
- show confidence and evidence

1. Checkpoint plan prompt

- show first 4-6 operations (base profile, extrusion, fillets, hole pattern, mating strategy)

1. Printability prompt

- orientation, supports, tolerance band by joint type, split strategy if needed

1. Execute with approval

- one checkpoint at a time, with rollback option

1. Verify

- mass/size checks, fit assumptions, assembly mate sanity checks

### Example high-value options UI for U-bracket

- Bracket style: plain U / gusseted U / lightened pocketed U
- Joint style: through pin / shoulder bolt / captive nut pivot
- Fastener source strategy: user-provided dimensions vs catalog-driven placeholders
- Print profile: speed draft / balanced / strength priority

### Success criteria for this demo

- Correct family and delegation chosen before modeling
- User can inspect evidence for each key decision
- At least one correction loop completes without losing model state
- Final part(s) fit printer envelope and tolerance assumptions are explicit

---

## Next Action Items (Prioritized)

1. Implement dedicated feature-tree reconstruction skill file and bind it to inspect-classify-delegate triggers.
2. Add a docs page with "family-gated tool shortlist" tables used by orchestrator prompts.
3. Extend SQLite schema to include `design_sessions`, `plan_checkpoints`, and `tool_calls`.
4. Add `capture_part_state` workflow output as structured JSON fixture for benchmark parts.
5. Create Prefab/FastMCP UI POC page for classification approval and checkpoint execution.
6. Build benchmark set entries for Baseball Bat, U-Joint Pin, Paper Airplane, and U-bracket assembly.
7. Add evaluation scripts for: family accuracy, first-feature correctness, correction count before valid build.
8. Add printability rubric (material/nozzle/layer-height aware) to checkpoint verification.

---

## Open Questions

1. Should the first UI POC be pure Prefab, FastMCP native app UI, or a hybrid where Prefab is optional?
2. Which U-bracket variant should be canonical for the benchmark (single-part clamp bracket vs multi-part hinge bracket)?
3. Do we want a strict "no execute until family accepted" hard gate in code, or a soft warning gate during early experimentation?
