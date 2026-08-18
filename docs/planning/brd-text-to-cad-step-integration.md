# Business Requirements Document: Text-to-CAD STEP Integration

**Status:** Draft — for review before OpenSpec proposal
**Last updated:** 2026-08-18
**Related issue:** [#43 — feat(tools): integrate text-to-cad 'cad' skill as STEP-first generation branch](https://github.com/andrewbartels1/SolidworksMCP-python/issues/43)
**Related issues (context, not blocking):** #42 (skill-routing layer, **now shipped** — see Section 8), #44 (CADAM-inspired live UI)
**Source research:** [`docs/planning/text-to-cad-cadam-integration-report.md`](text-to-cad-cadam-integration-report.md), plus direct inspection of [`earthtojake/text-to-cad`](https://github.com/earthtojake/text-to-cad) (2026-08-18)

---

## 1. Executive Summary

This repository is, and remains, a SolidWorks automation MCP server — that does not change. What this BRD proposes is pairing it with the external, MIT-licensed `earthtojake/text-to-cad` skill library so the two work together across **three pathways**, not the single one originally scoped:

1. **Inbound generation**: the `cad` skill generates a validated STEP file (build123d-based, STEP-first, with a mandatory inspect/snapshot validation loop) from a natural-language request; this repo imports it as a live, editable SolidWorks document.
2. **Outbound preview/validation**: this repo's *existing* `export_step` tool produces a STEP file from SolidWorks-native work; that path is handed to the `cad-viewer` skill (a format-agnostic local browser viewer) and the `cad` skill's own `scripts/inspect` for geometric review — free preview/validation tooling this repo doesn't have to build itself.
3. **Parts sourcing**: the `step-parts` skill finds and downloads real off-the-shelf hardware (screws, bearings, motors, connectors) as STEP files from a hosted catalog; the same import path (pathway 1's tool) drops the result into a SolidWorks assembly instead of the user hand-modeling standard hardware.

All three pathways share one property that keeps this repo's own footprint small: **`earthtojake/text-to-cad`'s inspect/snapshot/viewer/parts tooling operates on STEP files as files** — it does not care whether a given STEP came from its own build123d generator, from `step.parts`, or from this repo's own SolidWorks export. Only pathway 1's *generation step* (`scripts/gen`) is build123d-specific; everything else is format-driven and reusable in both directions.

The key finding from prior research still holds and now applies to all three pathways: **no SolidWorks-adapter or COM code changes are required.** `open_model` already opens STEP files; `export_step` already produces them. What's missing is the glue - one new handoff tool plus router/documentation wiring - that makes all three pathways documented, discoverable, and validated instead of something that only works if a user happens to know both toolchains exist and chains tools manually.

---

## 2. Problem Statement / Business Justification

- Users of this MCP server today can only produce geometry two ways: describe individual SolidWorks feature operations to an LLM one at a time (slow, error-prone for anything beyond simple shapes), or model by hand outside the assistant entirely (defeats the purpose of an MCP-driven workflow). Standard hardware (screws, bearings, connectors) has to be hand-modeled or sourced manually even though verified STEP files for exactly those parts are one API call away.
- A capable, validated text-to-CAD generator, a format-agnostic geometry viewer, and a real parts-catalog search already exist upstream (MIT-licensed, actively maintained, 12,961+ stars on the core repo). Rebuilding any of that in this repo - a generation engine, a browser viewer, a hardware catalog - would be redundant engineering effort with no differentiation. The differentiated value this project offers is the SolidWorks-native execution and verification layer downstream of wherever geometry comes from, not geometry generation, visualization, or parts cataloging themselves.
- Without this integration, three categories of request either get refused, hand-rolled through primitive feature-creation tools, or done outside the assistant entirely: "generate me a bracket with these dimensions," "let me see what this part looks like without opening SolidWorks," and "add a standard M3x12 socket head screw to this assembly." None of those showcase the MCP server's actual strength (deep, verified SolidWorks automation) - they're all preamble or periphery to it.

**Business outcome:** a user can describe a part in natural language and get back an editable SolidWorks document; can preview any SolidWorks-native work in a browser without a second tool; and can pull real off-the-shelf hardware into an assembly instead of hand-modeling it - with every pathway surfacing both the source skill's own validation artifacts (where applicable) and this repo's live model-info/feature-tree readback in one response.

---

## 3. Goals and Success Metrics

| Goal | Success Metric |
|---|---|
| Make text-to-CAD generation a documented, repeatable workflow | Setup steps exist in README/docs; a new user can go from zero to an imported STEP file by following them, without asking the maintainer |
| Close the loop between generation and verification | Every import returns both the source skill's own validation artifacts (when applicable - e.g. the `cad` skill's snapshot paths and `scripts/inspect` facts) and this repo's own `get_model_info`/`list_features` readback in a single tool response - no second round-trip needed |
| Give SolidWorks-native work a free preview/validation path | The skill router's `solidworks-native` branch documents the `export_step` → `$cad-viewer` handoff so a caller can generate a shareable browser preview link without building any new viewer code in this repo |
| Make standard-hardware sourcing a first-class alternative to hand-modeling | The `text-to-cad` branch's documentation covers the `step-parts` → import handoff explicitly, not just the generation path |
| Keep the SolidWorks-native tool surface authoritative | Zero changes to `pywin32_adapter.py`, `IntelligentRouter`, or `ComplexityAnalyzer`; every new piece is additive |
| Avoid silent unit/origin mismatches | Any conflict between the `cad` skill's conventions (mm units, XY base plane, +Z extrusion) and this repo's `create_part`/`create_extrusion` assumptions is documented with an explicit resolution, not discovered later as a bug |

---

## 4. Scope

### In scope

- Documented install/setup path for the relevant `text-to-cad` skills as an external dependency (Claude Code/Codex/Grok plugin, or `npx skills add earthtojake/text-to-cad`) - the `cad`, `cad-viewer`, and `step-parts` skills specifically; the library has others (URDF, SDF, G-code, Bambu Labs, etc.) that are out of scope here.
- One new MCP tool (working name `import_generated_step`) in `src/solidworks_mcp/tools/file_management.py` that:
  - Wraps `open_model` for STEP import, regardless of whether the STEP came from the `cad` skill's generator or `step-parts`' catalog download - the tool doesn't need to know or care which.
  - Immediately runs `get_model_info` + `list_features` and returns them alongside the import result.
  - Accepts and surfaces an optional caller-supplied validation/provenance report (the `cad` skill's snapshot/inspect artifacts, or a `step-parts` catalog record) without parsing or validating its contents.
  - Accepts an optional `part_family` free-text tag for the caller's own provenance/bookkeeping (see Section 9 for what this is for).
- Router documentation (in `get_skill_route`'s `text-to-cad` branch and `solidworks-native` branch) covering all three pathways: generation-then-import, sourcing-then-import, and export-then-preview. This is documentation/`validation_steps` content, not new code - the actual skill invocations (`$cad-viewer`, `$step-parts`) happen client-side, in the calling model's own session, using tools this repo doesn't control.
- Mock-adapter coverage for the new tool (per this repo's existing test-tiering convention) and a `solidworks_only` real-integration test, generating its own round-trip STEP fixture rather than depending on either upstream skill being installed in CI.
- Documentation of the unit/origin convention boundary between the `cad` skill's defaults and this repo's part-creation tools.
- The `allowed_tools` allowlist for the `text-to-cad` router branch, wired live now that #42 is shipped (see Section 8 - this is a change from the original BRD).

### Out of scope

- Any change to the COM adapter, `IntelligentRouter`, or `ComplexityAnalyzer`.
- Reimplementing any part of the `cad` skill's build123d generation logic, the `cad-viewer` server, or the `step-parts` catalog/API - all three stay external dependencies, never vendored.
- Hosting, wrapping, or proxying `$cad-viewer` or `$step-parts` from within this repo's own MCP server process. This repo never calls those services directly; it only produces/consumes the STEP files they operate on, and documents the handoff for the calling model to perform using its own installed skills.
- Assembly-level `AssemblyHelper`/build123d-joint handoff - v1 is single-part/single-component STEP import only.
- Issue #44's live-render UI - no UI work here; this ships as MCP tools plus router documentation only.

---

## 5. Stakeholders

| Stakeholder | Interest |
|---|---|
| Repo maintainer (Andrew Bartels) | Final sign-off on scope, on the "documented external dependency vs. vendored" decision, on tool naming, and on `part_family`'s exact meaning |
| End users of the MCP server (via Claude Code / Claude Desktop / other MCP clients) | Get a working generate-then-edit, source-then-assemble, and export-then-preview workflow without needing to know three toolchains exist separately |
| Future implementers of #44 (live UI) | Will eventually want to render this tool's validation/readback payload, and possibly embed `$cad-viewer` links, in the live activity panel |

---

## 6. Functional Requirements

1. A documented setup path exists for installing the `cad`, `cad-viewer`, and `step-parts` skills (README or `docs/` page), including the known install methods (Skills CLI `npx skills add`, or the Claude Code/Codex/Grok plugin installers).
2. `import_generated_step(step_path: str, part_family: str | None = None, validation_report: dict[str, Any] | None = None) -> dict[str, Any]` is implemented, importing via the existing `open_model` path, and works identically regardless of whether `step_path` came from the `cad` skill's generator or a `step-parts` download.
3. The tool's response includes, at minimum:
   - Import status (mirrors this repo's stable `{status, message, execution_time, data}` payload shape).
   - Post-import `get_model_info` output.
   - Post-import `list_features` output.
   - The caller-supplied `validation_report`, passed through unmodified if present.
   - The caller-supplied `part_family` tag, passed through unmodified if present.
4. The tool is covered by mock-adapter unit tests and a `solidworks_only`-tagged real-integration test, consistent with this repo's existing test-tiering convention (see `CLAUDE.md` testing guidance).
5. The `text-to-cad` branch of `get_skill_route` (#42, shipped) returns a live, non-stub route: `allowed_tools` includes `import_generated_step`, `get_model_info`, `list_features`; `fallback` is `null`; `validation_steps` documents both the generation-then-import and sourcing-then-import pathways.
6. The `solidworks-native` branch of `get_skill_route` documents the export-then-preview pathway: after `export_step`, hand the returned absolute path to `$cad-viewer` (when installed) for a browser preview link.

---

## 7. Non-Functional Requirements

- **No COM/adapter risk introduced**: the new tool must go through `open_model` and existing adapter methods only - no new direct COM calls, no new threading surface.
- **Fails closed on ambiguity**: if the STEP file fails to open, the tool must return a clear failure status rather than silently proceeding. `validation_report`/`part_family` absence is never a failure condition - both are optional.
- **No dependency vendoring**: none of `cad`, `cad-viewer`, or `step-parts` source is ever copied into this repo; all three are referenced as external, user-installed dependencies only.
- **No new network dependency for this repo itself**: `step-parts` calls a hosted API (`api.step.parts`), but that call is made by the `step-parts` skill in the calling model's own session, not by this MCP server's Python process. This repo's own test suite and runtime never make that network call.

---

## 8. Dependencies and Sequencing Risk

**This section is now resolved** - kept for the historical record of how the sequencing question was worked through.

Issue #43's own text originally said the tool should be "wired as the text-to-cad branch in the #42 router." Issue #42 was open and unimplemented when this BRD was first drafted (2026-08-12), creating a one-directional dependency risk documented in the original version of this section.

**Resolution (as of 2026-08-18): #42 has shipped.** `cad-skill-router` is complete (`get_skill_route` MCP tool, 12/12 tasks done, no UI, no internal LLM call - see `openspec/changes/cad-skill-router/`). The router-wiring acceptance criterion that was previously deferred is back in scope for this change and should be satisfied directly: the `text-to-cad` branch's `allowed_tools`/`fallback` gets updated from its current stub to a live route as part of this change, not filed as separate follow-up work.

**Other dependencies:**

- No dependency on #44 (live UI) - that issue would consume this tool's output later, but nothing here depends on it.
- Soft dependency on #41 (already merged) - the live-readback fix that guarantees `get_model_info`/`list_features` return fresh data. Already in place.

---

## 9. Assumptions

- The user installs the relevant `text-to-cad` skills themselves (documented external dependency) rather than this repo vendoring or auto-installing any of them.
- `open_model`'s existing STEP-import path is sufficient for both the `cad` skill's generated output and `step-parts`' catalog downloads without modification - this was verified by prior research for generated STEP but should be re-confirmed against a live SolidWorks session as part of implementation for both provenances (mirrors the pattern from the assembly-aware `list_features` change, where mock-only tests missed two live-only COM bugs).
- The `cad` skill's default conventions (mm units, XY base plane, +Z extrusion axis) are compatible with, or can be explicitly reconciled with, this repo's part-creation conventions without requiring a conversion layer. STEP is a self-describing format (ISO 10303 unit block), so `OpenDoc6` handles unit conversion regardless of authoring units; orientation is not auto-corrected and is documented as such, not silently assumed correct.
- **`part_family` resolution**: there is no upstream or internal spec defining this field's meaning - it was carried forward from issue #43's original proposed signature without explanation. The best-supported interpretation, based on `step-parts`' own API using `family` as a real facet name (e.g. `family=feetech`), is: a free-text provenance/categorization tag - either passed through from a `step-parts` search's `family` facet for a sourced part, or assigned by the calling model for a custom-generated part (e.g. `"bracket"`, `"enclosure"`). It is accepted and echoed back, never parsed or validated by this tool, exactly like `validation_report`. This is a judgment call, not a confirmed upstream contract - flagged for maintainer sign-off in Section 11.

---

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Unit/origin convention mismatch between `cad` skill output and this repo's part-creation tools | Medium | Medium - could cause silently-wrong-scale imports | Explicit reconciliation step in requirements (Section 6); verify against a live import before calling the change done |
| Upstream skill contracts change (paths, script names, output format, `step-parts` API shape) | Low | Medium | Treated as external dependencies with a documented version/commit reference at time of integration, not pinned/vendored |
| `step-parts` is a hosted, internet-dependent service outside this repo's control | Low-Medium | Low | This repo never calls it directly (Section 7); an outage only affects the calling model's ability to source a part, not this repo's own tool contract or tests |
| Live-only COM bugs in the `open_model`/STEP path not caught by mock tests | Medium (precedent: this happened in the assembly-aware `list_features` change) | Medium | Tasks.md for the resulting change should include an explicit live-verification task, not just mock coverage |
| `part_family`'s meaning (Section 9) turns out to not match what the maintainer actually intended in issue #43 | Low | Low - it's an optional, unvalidated passthrough field either way | Flagged explicitly for sign-off rather than silently assumed; cheap to rename or drop later since nothing parses it |

---

## 11. Open Questions (carry into OpenSpec proposal)

1. ~~Tool location~~ - resolved: `src/solidworks_mcp/tools/file_management.py`, next to `get_model_info`/`list_features` (two of its three composed adapter calls already live there).
2. ~~Should this block on #42?~~ - resolved: #42 shipped; router wiring is in scope directly (Section 8).
3. **`part_family`'s meaning** - Section 9 gives a best-supported interpretation (free-text provenance tag, possibly mirroring `step-parts`' `family` facet). Needs explicit maintainer confirmation, not just inference from the upstream API's naming.
4. Exact tool/parameter naming: is `import_generated_step` still the best name now that it also covers `step-parts`-sourced (not generated) parts? Alternatives: `import_step_file` (source-agnostic) vs. keeping the current name since the *operation* (open + readback) is identical regardless of provenance and "generated" can be read loosely as "produced outside this repo."
5. Should the documented setup instructions for all three skills live in the top-level README or under `docs/`? (Existing convention favors `docs/` for anything beyond a quick-start pointer.)

---

## 12. Acceptance Criteria

- [ ] Documented install/setup steps exist for the `cad`, `cad-viewer`, and `step-parts` skills (README or `docs/`).
- [ ] `import_generated_step` (or equivalent) tool implemented, unit-tested with the mock adapter, and covered by a `solidworks_only` real-SolidWorks test that generates its own round-trip STEP fixture.
- [ ] Response includes both the source skill's validation/provenance artifacts (when supplied) and this repo's own post-import `get_model_info`/`list_features` readback.
- [ ] `text-to-cad` branch of `get_skill_route` returns a live route (not a stub) with `allowed_tools` covering the new tool plus readback tools.
- [ ] `solidworks-native` branch of `get_skill_route` documents the `export_step` → `$cad-viewer` preview handoff.
- [ ] Unit/origin convention mismatches (if any) documented with a resolution, not silently ignored.
- [ ] `part_family`'s meaning (Section 9/11.3) confirmed with the maintainer, not left as an inferred guess in shipped code comments.

---

## 13. Recommended Next Step

Update the `text-to-cad-step-integration` OpenSpec change's `proposal.md` and `design.md` (already drafted, now stale relative to this BRD's expanded three-pathway scope) to match this BRD, then re-run the design-review checkpoint before writing `tasks.md`.
