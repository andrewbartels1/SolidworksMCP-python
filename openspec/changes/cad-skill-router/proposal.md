## Why

This repo can generate CAD three fundamentally different ways — editable SolidWorks-native modeling, text-to-cad STEP-first generation (issue #43, not yet implemented), and future mesh-concept generation — but there is no structured way for the assistant to decide which one a given request should use. Without an explicit classification step, either the LLM has to guess, the tool surface grows unconstrained as new branches are added (the source research report, `docs/planning/text-to-cad-cadam-integration-report.md`, is explicit that this makes the LLM worse, not better), or users have to already know which workflow to ask for. This change adds the thin routing layer the report recommends, so #43 and any future generation branch plug in as named branches instead of separate, uncoordinated entry points. Addresses [issue #42](https://github.com/andrewbartels1/SolidworksMCP-python/issues/42).

## What Changes

- Add a `classify_skill_family` service (working shape: a `SkillRoute` dataclass with `family`, `allowed_tools`, `validation_steps`, `expected_outputs`, `fallback`, `confidence`) that classifies a user's CAD-generation intent into one of three named branches: `solidworks-native`, `text-to-cad`, `mesh-concept`.
- New module `src/solidworks_mcp/ui/services/skill_router.py`, called from the existing clarify/inspect/go pipeline in `src/solidworks_mcp/ui/services/llm_service.py`, immediately before `run_go_orchestration` dispatches tool calls.
- `allowed_tools` on the returned route is validated against the `SolidWorksAdapter` interface (`src/solidworks_mcp/adapters/base.py`) at call time, not a hardcoded list — fails closed (excludes) any name that isn't a real adapter capability, so the router can never let the model invent a tool. (Originally scoped as an MCP `list_tools()` check; revised during design review — see design.md Decision 3 for why the adapter interface is the correct validation source, not the MCP tool catalog.)
- The `solidworks-native` branch routes unchanged through the existing `llm_service.py` pipeline and `IntelligentRouter`/`ComplexityAnalyzer` (`src/solidworks_mcp/adapters/intelligent_router.py`, `complexity_analyzer.py`) — this change does not duplicate or replace that COM/VBA-level routing, it sits one level above it.
- `text-to-cad` and `mesh-concept` branches ship as stubbed/feature-flagged (always low-confidence or explicitly disabled) in this change, since neither has a backing implementation yet — #43 is intentionally sequenced *after* this change specifically so it can wire the real `text-to-cad` branch into a router that already exists, instead of this change stubbing around a nonexistent one.
- A low-confidence fallback path is required: when the router can't confidently classify a request, it must say so rather than guessing a branch.

## Capabilities

### New Capabilities
- `agents/skill-router`: classification of CAD-generation user intent into named skill-family branches (`solidworks-native` / `text-to-cad` / `mesh-concept`), each with a validated tool allowlist, required validation steps, expected outputs, and a low-confidence fallback.

### Modified Capabilities
(none — this change adds a new capability; it calls into `llm_service.py`'s existing clarify/inspect/go pipeline as a new step but does not change that pipeline's own external contract)

## Impact

- New file: `src/solidworks_mcp/ui/services/skill_router.py`.
- Integration point (call site only, no internal logic changes): `src/solidworks_mcp/ui/services/llm_service.py`, between its existing `inspect_family` step and `run_go_orchestration`.
- **Does not touch COM/adapter code.** No changes to `pywin32_adapter.py`, the base adapter interface, or `mock_adapter.py`. The `solidworks-native` branch dispatches through the existing, unchanged `IntelligentRouter`/`ComplexityAnalyzer` path.
- Runtime dependency: import access to `src/solidworks_mcp/adapters/base.py`'s `SolidWorksAdapter` interface at classification time (no cross-process or MCP-protocol dependency).
- No breaking changes to any existing tool or adapter contract. `text-to-cad` and `mesh-concept` branches are additive stubs in this change; #43 fills in `text-to-cad` for real afterward using this change's allowlist/contract rather than redefining it.
