# Business Requirements Document: Text-to-CAD STEP Integration

**Status:** Draft — for review before OpenSpec proposal
**Last updated:** 2026-08-12
**Related issue:** [#43 — feat(tools): integrate text-to-cad 'cad' skill as STEP-first generation branch](https://github.com/andrewbartels1/SolidworksMCP-python/issues/43)
**Related issues (context, not blocking):** #42 (skill-routing layer), #44 (CADAM-inspired live UI)
**Source research:** [`docs/planning/text-to-cad-cadam-integration-report.md`](text-to-cad-cadam-integration-report.md)

---

## 1. Executive Summary

Today, turning a natural-language description into an editable SolidWorks part requires a human to model it by hand, feature by feature. This BRD proposes closing that gap by adopting `earthtojake/text-to-cad` — an MIT-licensed, actively maintained (12,961 stars) CAD-generation skill — as an external dependency, and adding one new MCP tool that imports its validated STEP output into SolidWorks with an automatic model-info/feature-tree readback.

The key finding from prior research is that **no SolidWorks-adapter or COM code changes are required**: `open_model` already opens STEP files. What's missing is the glue that makes this a documented, discoverable, validated workflow instead of something that only works if a user happens to chain two tools manually.

This is scoped as a standalone, shippable capability. It does **not** require issue #42's skill-routing layer to exist first, even though #43's original issue text describes it as a router branch — see [Section 8](#8-dependencies-and-sequencing-risk) for why, and how this BRD resolves that tension.

---

## 2. Problem Statement / Business Justification

- Users of this MCP server today can only produce geometry two ways: describe individual SolidWorks feature operations to an LLM one at a time (slow, error-prone for anything beyond simple shapes), or model by hand outside the assistant entirely (defeats the purpose of an MCP-driven workflow).
- A capable, validated text-to-CAD generator already exists upstream (MIT-licensed, STEP-first, with a mandatory geometric-validation loop before handoff). Rebuilding that generation capability in this repo would be redundant engineering effort with no differentiation — the differentiated value this project offers is the SolidWorks-native execution and verification layer downstream of geometry generation, not geometry generation itself.
- Without this integration, every "generate me a bracket with these dimensions" request either gets refused, hand-rolled through primitive feature-creation tools, or done outside the assistant — none of which showcase the MCP server's actual strength (deep, verified SolidWorks automation).

**Business outcome:** a user can describe a part in natural language and get back an editable SolidWorks document, with both the generator's own validation artifacts and this repo's live model-info/feature-tree readback surfaced in one response — turning "generate CAD" from an unsupported request into a first-class, verified workflow.

---

## 3. Goals and Success Metrics

| Goal | Success Metric |
|---|---|
| Make text-to-CAD generation a documented, repeatable workflow | Setup steps exist in README/docs; a new user can go from zero to an imported STEP file by following them, without asking the maintainer |
| Close the loop between generation and verification | Every import returns both the `cad` skill's validation artifacts (snapshot paths, `scripts/inspect` facts) and this repo's own `get_model_info`/`list_features` readback in a single tool response — no second round-trip needed |
| Keep the SolidWorks-native tool surface authoritative | Zero changes to `pywin32_adapter.py`, `IntelligentRouter`, or `ComplexityAnalyzer`; the new tool is additive only |
| Avoid silent unit/origin mismatches | Any conflict between the `cad` skill's conventions (mm units, XY base plane, +Z extrusion) and this repo's `create_part`/`create_extrusion` assumptions is documented with an explicit resolution, not discovered later as a bug |

---

## 4. Scope

### In scope

- Documented install/setup path for the `text-to-cad` `cad` skill as an external dependency (Claude Code/Codex plugin, or `npx skills install`).
- One new MCP tool (working name `import_generated_step`) in `src/solidworks_mcp/tools/file_management.py` or `modeling.py` that:
  - Wraps `open_model` for STEP import.
  - Immediately runs `get_model_info` + `list_features` and returns them alongside the import result.
  - Accepts and surfaces the `cad` skill's own validation report (snapshot paths, inspect facts) if provided by the caller.
- Mock-adapter coverage for the new tool (per this repo's existing test-tiering convention) and a `solidworks_only` real-integration test.
- Documentation of the unit/origin convention boundary between the `cad` skill's defaults and this repo's part-creation tools.
- An explicit, hardcoded `allowed_tools` allowlist for this workflow (`import_generated_step`, `get_model_info`, `list_features`, plus whatever else the acceptance criteria settle on) — defined locally in this change, **not** wired into a live router, since #42 doesn't exist yet (see Section 8).

### Out of scope

- Any change to the COM adapter, `IntelligentRouter`, or `ComplexityAnalyzer`.
- Reimplementing any part of the `cad` skill's build123d generation or validation logic — it stays an external dependency, not vendored code.
- Assembly-level `AssemblyHelper`/build123d-joint handoff — v1 is single-part STEP import only.
- Building or modifying issue #42's actual router implementation. This BRD only reserves the shape (a named allowlist) that a future router can consume.
- Issue #44's live-render UI — no UI work here; this ships as an MCP tool only.

---

## 5. Stakeholders

| Stakeholder | Interest |
|---|---|
| Repo maintainer (Andrew Bartels) | Final sign-off on scope, on the "documented external dependency vs. vendored" decision, and on where the new tool lives |
| End users of the MCP server (via Claude Code / Claude Desktop / other MCP clients) | Get a working generate-then-edit workflow without needing to know both toolchains exist separately |
| Future implementers of #42 (skill router) | Need this issue's `allowed_tools` allowlist and tool contract to be stable enough to consume without a breaking change |
| Future implementers of #44 (live UI) | Will eventually want to render this tool's validation/readback payload in the live activity panel |

---

## 6. Functional Requirements

1. A documented setup path exists for installing the `text-to-cad` `cad` skill (README or `docs/` page), including the two known install methods (Claude Code plugin marketplace, or `npx skills install`).
2. `import_generated_step(step_path: str, part_family: str | None, validation_report: dict | None) -> dict[str, Any]` (or equivalently named/shaped tool) is implemented, importing via the existing `open_model` path.
3. The tool's response includes, at minimum:
   - Import status (mirrors this repo's stable `{status, message, execution_time, ...}` payload shape).
   - Post-import `get_model_info` output.
   - Post-import `list_features` output.
   - The caller-supplied `validation_report` (the `cad` skill's own snapshot/inspect artifacts), passed through unmodified if present.
4. The tool is covered by mock-adapter unit tests and a `solidworks_only`-tagged real-integration test, consistent with this repo's existing test-tiering convention (see `CLAUDE.md` testing guidance).
5. A defined `allowed_tools` allowlist for this workflow is documented in the change's spec, scoped to exactly what the text-to-cad path needs (not the full 112-tool SolidWorks-native surface).

---

## 7. Non-Functional Requirements

- **No COM/adapter risk introduced**: the new tool must go through `open_model` and existing adapter methods only — no new direct COM calls, no new threading surface. This keeps it outside the high-risk category flagged by `openspec/config.yaml`'s proposal rules, but the OpenSpec proposal for this change should still explicitly state "does not touch COM/adapter code" so that rule is satisfied by an explicit statement, not an omission.
- **Fails closed on ambiguity**: if `validation_report` is absent or the STEP file fails to open, the tool must return a clear failure status rather than silently proceeding.
- **No dependency vendoring**: the `cad` skill's source is never copied into this repo; it is referenced as an external, user-installed dependency only.

---

## 8. Dependencies and Sequencing Risk

**This is the most important thing to get right before starting implementation, and the reason this BRD exists rather than jumping straight to a proposal.**

Issue #43's own text says the tool should be "wired as the text-to-cad branch in the #42 router," and lists that as an acceptance criterion. But issue #42 (the router) is still open and unimplemented — its own acceptance criteria explicitly allow `text-to-cad` and `mesh-concept` branches to be "stubbed/feature-flagged until #43 lands," meaning #42 does not block on #43. There is no equivalent statement in #43 saying it doesn't block on #42, which creates a one-directional dependency risk: if this BRD's scope is read literally, #43 can't be marked fully done until #42 exists.

**Resolution adopted by this BRD:** decouple the two.

- `import_generated_step` ships as a directly callable MCP tool, usable today without any router — this satisfies the actual business goal (users can generate-then-edit right now) independent of #42's timeline.
- The `allowed_tools` allowlist for the text-to-cad branch is still defined and documented as part of this change (satisfies #43's intent), but it's a static list living in this change's spec, not a live integration with a router that doesn't exist yet.
- The specific acceptance criterion "wired as the text-to-cad branch in the #42 router" is treated as **deferred to whichever change implements #42**, not as a blocking requirement of this change. That future change should reuse the allowlist and tool contract defined here rather than redefining it.

**Other dependencies:**

- No dependency on #44 (live UI) — that issue consumes this tool's output later, but nothing here depends on it.
- Soft dependency on #41 (already merged) — the live-readback fix that guarantees `get_model_info`/`list_features` return fresh data. This is already in place, so no action needed here beyond relying on it.

---

## 9. Assumptions

- The user installs the `text-to-cad` `cad` skill themselves (documented external dependency) rather than this repo vendoring or auto-installing it.
- `open_model`'s existing STEP-import path is sufficient for the `cad` skill's STEP output without modification — this was verified by prior research but should be re-confirmed against a live SolidWorks session as part of implementation (mirrors the pattern from the assembly-aware `list_features` change, where mock-only tests missed two live-only COM bugs).
- The `cad` skill's default conventions (mm units, XY base plane, +Z extrusion axis) are compatible with, or can be explicitly reconciled with, this repo's part-creation conventions without requiring a conversion layer. If reconciliation turns out to need actual conversion logic, that's a scope increase this BRD does not currently account for.

---

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Unit/origin convention mismatch between `cad` skill output and this repo's part-creation tools | Medium | Medium — could cause silently-wrong-scale imports | Explicit reconciliation step in requirements (Section 6.5); verify against a live import before calling the change done |
| `text-to-cad` upstream changes its skill contract (paths, script names, output format) | Low | Medium | Treated as an external dependency with a documented version/commit reference at time of integration, not pinned/vendored |
| Scope creep toward "also build the router" since the issue text mentions #42 | Medium | High (turns a bounded change into an unbounded one) | Section 8's explicit decoupling; OpenSpec proposal for this change should state the router is out of scope |
| Live-only COM bugs in the `open_model`/STEP path not caught by mock tests | Medium (precedent: this happened in the assembly-aware `list_features` change) | Medium | Tasks.md for the resulting change should include an explicit live-verification task, not just mock coverage |

---

## 11. Open Questions (carry into OpenSpec proposal)

1. Tool location: `src/solidworks_mcp/tools/file_management.py` (next to `open_model`) or `modeling.py`? Recommend `file_management.py` since `open_model` already lives there.
2. Exact tool/parameter naming: is `import_generated_step` the final name, or should it follow a different existing naming convention in the tools module?
3. Should the documented setup instructions live in the top-level README or under `docs/`? (Existing convention favors `docs/` for anything beyond a quick-start pointer.)

---

## 12. Acceptance Criteria

Carried forward from issue #43, adjusted per Section 8's decoupling:

- [ ] Documented install/setup steps for the `text-to-cad` skill exist in this repo (README or `docs/`).
- [ ] `import_generated_step` (or equivalent) tool implemented, unit-tested with the mock adapter, and covered by a `solidworks_only` real-SolidWorks test.
- [ ] Response includes both the `cad` skill's validation artifacts and this repo's own post-import `get_model_info`/`list_features` readback.
- [ ] `allowed_tools` allowlist for the text-to-cad branch is defined and documented in this change's spec (static, not wired into a live router).
- [ ] Unit/origin convention mismatches (if any) documented with a resolution, not silently ignored.
- [ ] ~~Wired as the text-to-cad branch in the #42 router~~ — **deferred**; tracked as follow-up work for whichever change implements #42, per Section 8.

---

## 13. Recommended Next Step

Run `/opsx:propose text-to-cad-step-integration` to generate the OpenSpec proposal/specs/design/tasks for this change, using this BRD as the source of truth for scope and the Section 8 sequencing decision. The new design-review checkpoint (added to `/opsx:propose` alongside this BRD) will prompt for gaps in `design.md` before `tasks.md` is created — use it.
