## Revision note (2026-08-15)

This change was originally implemented against a dashboard/LLM-driven design (see `proposal.md`'s Revision note and `design.md` for why). That design was rebuilt from scratch as a plain MCP tool after `src/solidworks_mcp/ui/` was deleted from the repo. The task list below reflects the **current** (tool-based) implementation, done in a single pass rather than the original six-section plan — recorded here as what was actually done, not a checklist to re-walk.

## 1. Core module and MCP tool

- [x] 1.1 Create `src/solidworks_mcp/tools/skill_router.py` following this
      repo's standard tool-module pattern (`async def register_skill_router_tools(mcp, adapter, config) -> int`,
      registered in `src/solidworks_mcp/tools/__init__.py`).
- [x] 1.2 Define `SkillRouteInput` (a `CompatInput` subclass) with a single
      `family: Literal["solidworks-native", "text-to-cad", "mesh-concept"]`
      field, whose description covers what each branch means so the calling
      model can classify correctly without a nested LLM call.
- [x] 1.3 Register a single `@mcp.tool() get_skill_route(input_data: SkillRouteInput) -> dict[str, Any]`
      tool returning this repo's standard `{status, message, execution_time, data}`
      payload shape, with `data` holding `family`/`allowed_tools`/
      `validation_steps`/`expected_outputs`/`fallback`.

## 2. Adapter-capability validation

- [x] 2.1 `_adapter_capability_names()`: plain class introspection over
      `SolidWorksAdapter` (`src/solidworks_mcp/adapters/base.py`) — every
      public, callable, non-underscore-prefixed attribute. No running
      process, no network call.
- [x] 2.2 `filter_to_adapter_capabilities()`: fail-closed allowlist filter —
      given a proposed list of tool names, returns only the ones that are
      real adapter capabilities, order preserved, never raises on an
      unknown name.
- [x] 2.3 Unit tests: a real adapter method name passes through unchanged;
      a made-up name is silently excluded; a mixed list keeps only the real
      names in original order.

## 3. Per-branch route construction

- [x] 3.1 `solidworks-native` branch: `allowed_tools` is
      `sorted(_adapter_capability_names())` (the full adapter capability
      set, per design.md Decision 4 — no curated subset), with
      `validation_steps`/`expected_outputs` populated from the integration
      report's Workflow A guardrails (inspect before execute, verify by
      artifact), `fallback: None`.
- [x] 3.2 `text-to-cad` / `mesh-concept` branches (stubs): `allowed_tools: []`,
      `fallback` states explicitly that the branch has no backing
      implementation yet (`text-to-cad`'s message references issue #43).

## 4. Tests

- [x] 4.1 `tests/solidworks_mcp/tools/test_skill_router.py`: tool
      registration count, `solidworks-native` returns the full live adapter
      capability set (regression-guarded against `SolidWorksAdapter`
      directly, so a future adapter-interface change can't silently drift),
      `text-to-cad`/`mesh-concept` return correctly-flagged stubs, plus the
      adapter-capability-filter unit tests from Task 2.3.
- [x] 4.2 Added `get_skill_route` to `ADAPTER_FREE_TOOLS` in
      `tests/solidworks_mcp/tools/test_no_fabricated_payloads.py` (PR #52's
      AST-based guard against tools that never reach the adapter) — this
      tool legitimately never touches a live adapter instance, only the
      `SolidWorksAdapter` class itself, and does real, correct work either
      way.

## 5. Documentation and verification

- [x] 5.1 Ran the full mock test suite
      (`pytest tests/ -m "not solidworks_only and not smoke" -n 4`) after
      this change plus the `ui/` deletion it landed alongside: 1409 passed,
      21 skipped, 0 failures. Lint clean on every changed file.
- [x] 5.2 Rewrote `proposal.md`/`design.md`/`specs/agents/skill-router/spec.md`
      to describe the tool-based design rather than leaving them describing
      the deleted dashboard integration — an OpenSpec change's artifacts
      are supposed to be the source of truth for what was actually built.
