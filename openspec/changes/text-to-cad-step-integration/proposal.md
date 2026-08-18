## Why

See `docs/planning/brd-text-to-cad-step-integration.md` (rewritten 2026-08-18 after direct inspection of the upstream `earthtojake/text-to-cad` repo) for full background. Summary: this repo's skill router (#42, shipped) has a `text-to-cad` branch that is currently a stub - `get_skill_route(family="text-to-cad")` returns `allowed_tools: []` with a fallback pointing at this issue. This change closes that gap, and does it across all three pathways the BRD identifies rather than the single inbound-generation pathway originally scoped: generation (external `cad` skill → this repo), sourcing (external `step-parts` skill → this repo), and preview (this repo → external `cad-viewer`/`inspect` tooling). All three share one tool composition (`open_model` + `get_model_info` + `list_features`, or `export_step` already returning an absolute path) because the upstream skills' non-generation tooling operates on STEP files as files, not on how they were produced. Addresses [issue #43](https://github.com/andrewbartels1/SolidworksMCP-python/issues/43), sequenced after #42.

## What Changes

- Add an `import_generated_step` tool that imports a STEP file - regardless of whether it came from the `cad` skill's build123d generator or a `step-parts` catalog download - and returns a combined validation view: an optional caller-supplied provenance/validation report (never parsed, just echoed back) alongside this repo's own post-import readback (`get_model_info` + `list_features`), in a single round-trip. Internally composes the existing `open_model`, `get_model_info`, and `list_features` tools - **no new COM/adapter code**.
- Document the `cad`, `cad-viewer`, and `step-parts` skills (all part of the `earthtojake/text-to-cad` library) as external, user-installed dependencies (`claude plugin install cad@text-to-cad` / `npx skills add earthtojake/text-to-cad`), not vendored or pip-installed. This repo's Python dependency surface does not change, and this repo's own process never calls `step-parts`' hosted API or starts the `cad-viewer` server directly - those invocations happen client-side, in the calling model's own session.
- Update the skill router's `text-to-cad` branch (`src/solidworks_mcp/tools/skill_router.py`) so `get_skill_route(family="text-to-cad")` returns a live, non-stub route: `allowed_tools` covering `import_generated_step`, `get_model_info`, `list_features`; `validation_steps` documenting both the generation-then-import and sourcing-then-import pathways; `fallback: null`. This is a real update to already-shipped router code, made possible because #42 is now complete (unlike when this BRD was first drafted).
- Update the router's `solidworks-native` branch `validation_steps`/`expected_outputs` to document the export-then-preview pathway: after `export_step`, hand the returned absolute path to `$cad-viewer` (when installed) for a browser preview link, and to `scripts/inspect` for geometric review. No new tool needed - `export_step` already returns an absolute `file_path`.
- Document the unit/origin convention boundary between the `cad` skill's defaults (millimetres, XY base plane, +Z extrusion axis) and this repo's own `create_part`/`create_extrusion` conventions, with an explicit resolution: STEP's self-describing unit block means `OpenDoc6` handles unit conversion automatically regardless of authoring units; orientation is not auto-corrected.

No breaking changes - purely additive; every existing tool keeps its current contract.

## Capabilities

### New Capabilities
- `tools/import-generated-step`: STEP-file import tool that opens a STEP file from either the `cad` skill's generator or `step-parts`' catalog into a live SolidWorks document, returning a combined provenance + post-import-readback response.

### Modified Capabilities
(none filed as a formal delta - see "What Changes" above: the skill-router's `text-to-cad`/`solidworks-native` branch updates are implementation-level changes to already-shipped code, and `cad-skill-router`'s own capability spec is not yet archived under `openspec/specs/`, so there is no existing spec path to file a delta against.)

## Impact

- New tool module code: `import_generated_step` in `src/solidworks_mcp/tools/file_management.py` (colocated with `get_model_info`/`list_features`, two of its three composed adapter calls).
- `src/solidworks_mcp/tools/skill_router.py`: `text-to-cad` branch goes from stub to live route; `solidworks-native` branch gains export-then-preview documentation in its existing `validation_steps`.
- **Does not touch COM/adapter code.** No changes to `pywin32_adapter.py`, the base adapter interface, or `mock_adapter.py` - composes existing, already-adapter-backed tools only.
- New external dependencies: the `cad`, `cad-viewer`, and `step-parts` skills from the `earthtojake/text-to-cad` library (MIT licensed). Documented as user-installed prerequisites, not Python package dependencies. `step-parts` additionally depends on a hosted API (`api.step.parts`) that this repo's own process never calls.
- Docs: README and/or `docs/getting-started/` need an install note for all three skills and a description of the resulting three pathways.
- Test surface: mock-adapter-backed unit tests for `import_generated_step` (covering both STEP provenances), plus a `solidworks_only` real-SolidWorks test that generates its own round-trip STEP fixture (create_part → create_extrusion → export_step → import_generated_step) rather than depending on either upstream skill being installed in CI or a checked-in binary fixture.
