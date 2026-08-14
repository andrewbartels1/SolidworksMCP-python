## 1. Core types and module scaffold

- [ ] 1.1 Create `src/solidworks_mcp/ui/services/skill_router.py` with a frozen
      `SkillRoute` dataclass: `family: Literal["solidworks-native", "text-to-cad", "mesh-concept"]`,
      `allowed_tools: list[str]`, `validation_steps: list[str]`,
      `expected_outputs: list[str]`, `fallback: str | None`, `confidence: float`.
- [ ] 1.2 Add the `async def classify_generation_route(...)` signature (session_id,
      user_goal, plus the same `db_path`/`model_name` override pattern
      `inspect_family` already uses) returning `SkillRoute`.

## 2. Adapter-capability validation

- [ ] 2.1 Implement a helper that introspects `SolidWorksAdapter`
      (`src/solidworks_mcp/adapters/base.py`) for its public capability names
      (no running process, no network call — a plain class introspection).
- [ ] 2.2 Implement allowlist filtering: given a proposed list of tool names,
      return only the ones that are real adapter capabilities; never raise on
      an unknown name, just exclude it (fail closed per design.md Decision 3).
- [ ] 2.3 Mock-adapter-independent unit test: a real adapter method name
      passes through unchanged; a made-up name is silently excluded.

## 3. Classification implementation

- [ ] 3.1 Implement the LLM classification call, reusing `llm_service.py`'s
      existing model-call/provider-resolution infrastructure (the same
      pattern `inspect_family` already uses) — do not add a new provider or
      config path.
- [ ] 3.2 Apply a confidence threshold (initial value documented as tunable
      per design.md's Open Questions — pick one, e.g. 0.6, and note it's not
      load-bearing for the spec). Below threshold: populate `fallback` and
      treat the request as unresolved rather than committing to a branch.
- [ ] 3.3 Handle the LLM call itself failing (timeout/provider error): return
      `SkillRoute(confidence=0.0, fallback=<failure message>, allowed_tools=[])`
      per design.md Decision 7 — same shape as every other case, no separate
      exception type.

## 4. Per-branch route construction

- [ ] 4.1 `solidworks-native` branch: `allowed_tools` is the full adapter
      capability set from Task 2.1's helper (per design.md Decision 5 — no
      curated subset); populate `validation_steps`/`expected_outputs` from
      the report's Workflow A guardrails (inspect before execute, verify by
      artifact).
- [ ] 4.2 `text-to-cad` branch (stub): `allowed_tools: []`, `fallback` states
      explicitly that the branch is not yet implemented (references issue
      #43), `confidence` reflects the stub state rather than a real
      classification.
- [ ] 4.3 `mesh-concept` branch (stub): same stub pattern as 4.2, `fallback`
      states no backing implementation exists yet.

## 5. Integration with the orchestration pipeline

- [ ] 5.1 Call `classify_generation_route` from `llm_service.py`'s pipeline,
      positioned between the existing `inspect_family` step and
      `run_go_orchestration` (per design.md Context).
- [ ] 5.2 Confirm the exact point in `ui/services/checkpoint_service.py`
      (around its `create_adapter()` call, `checkpoint_service.py:219-220`)
      where the resulting route's `allowed_tools` should constrain what gets
      executed, and wire it there. This is genuinely new integration surface
      per design.md — verify against the real file structure before wiring,
      don't assume the exact call shape from this task list alone.
- [ ] 5.3 Verify `inspect_family`'s existing `family`/`proposed_family`
      naming (SolidWorks feature-tree classification) is untouched and
      remains unambiguous next to the new route's `family` field (design.md
      Decision 2) — no renames to the existing feature-tree classifier.

## 6. Tests

- [ ] 6.1 Unit tests for `classify_generation_route` covering all three
      branches with mocked LLM responses.
- [ ] 6.2 Unit test for the low-confidence fallback case.
- [ ] 6.3 Unit test for the LLM-call-failure fallback case.
- [ ] 6.4 Unit test for adapter-capability validation excluding a nonexistent
      tool name (Task 2.3, formalized as part of the suite).
- [ ] 6.5 Regression test asserting `solidworks-native`'s `allowed_tools`
      tracks the live `SolidWorksAdapter` capability set, so a future
      adapter-interface change can't silently drift from this route.

## 7. Documentation and verification

- [ ] 7.1 Run `.\dev-commands.ps1 dev-lint` and `.\dev-commands.ps1 dev-test`;
      confirm the mock-only suite passes with the existing coverage gate.
- [ ] 7.2 Document the `classify_generation_route`/`SkillRoute` contract
      (three branches, fallback semantics, adapter-capability validation) so
      #43 can wire a real `text-to-cad` branch against this change's shape
      instead of redefining it.
- [ ] 7.3 Note design.md's deferred open question (a future MCP-protocol
      caller needing MCP-tool-level validation instead of adapter-capability
      validation) near `classify_generation_route`, so it's discoverable if
      #43 or #44 ever need it.
