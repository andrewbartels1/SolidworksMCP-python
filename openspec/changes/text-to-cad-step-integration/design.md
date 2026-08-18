## Context

See `proposal.md` - Why, and `docs/planning/brd-text-to-cad-step-integration.md` for full background. This is the handoff tool the `cad-skill-router`'s (#42, shipped) `text-to-cad` branch was stubbed for, expanded to cover three pathways instead of one after direct inspection of `earthtojake/text-to-cad` (2026-08-18):

1. **Generation** (`cad` skill → this repo): build123d-generated, validated STEP → `import_generated_step`.
2. **Sourcing** (`step-parts` skill → this repo): catalog-downloaded STEP (real screws/bearings/motors/connectors) → same `import_generated_step`.
3. **Preview** (this repo → `cad-viewer`/`inspect`): `export_step`'s existing output → external viewer/inspection tooling.

Pathways 1 and 2 share one tool because `earthtojake/text-to-cad`'s non-generation tooling (`scripts/inspect`, `scripts/snapshot`, `cad-viewer`) is explicitly documented upstream as operating on STEP files regardless of provenance - "Both produce the same inspectable artifacts," per `skills/cad/SKILL.md`. Only `scripts/gen` (the generation step itself) is build123d-specific; nothing this repo touches is.

Existing pieces this change composes, unchanged:
- `open_model` (`src/solidworks_mcp/tools/modeling.py:429`) calls `adapter.open_model(file_path)` and already opens all SolidWorks-readable formats, including STEP, via `OpenDoc6`.
- `get_model_info` / `list_features` (`src/solidworks_mcp/tools/file_management.py:897`, `:932`) call `adapter.get_model_info()` / `adapter.list_features(...)` directly against the currently-active document.
- `export_step` (`src/solidworks_mcp/tools/export.py:389`) already returns an absolute `file_path` in its response - sufficient for pathway 3's viewer handoff with no new tool.
- All tools call their adapter method directly rather than through each other - no precedent in this codebase for one `@mcp.tool()` function calling another. This change follows that pattern.

The upstream `cad`, `cad-viewer`, and `step-parts` skills (all MIT, part of the `earthtojake/text-to-cad` plugin library) run entirely outside this repo's process, invoked by the calling model in its own session. This repo never calls any of them directly - not `api.step.parts`, not the `cad-viewer` Node server, not `scripts/gen`. It only produces or consumes the STEP files at the boundary.

## Goals / Non-Goals

**Goals:**
- A single tool, `import_generated_step`, that imports a STEP file from either upstream provenance (generated or sourced) and returns one merged response: the import result, a post-import `get_model_info`/`list_features` readback, and whatever provenance/validation artifacts the caller passes through.
- Wire this tool into the `text-to-cad` branch of `get_skill_route`, replacing the current stub.
- Document (not implement) the export-then-preview pathway in the `solidworks-native` branch's existing `validation_steps`.
- No new COM/adapter code, no new outbound network calls from this repo's own process.

**Non-Goals:**
- Re-validating or re-deriving upstream geometry (from either `cad` or `step-parts`). This tool trusts that the calling model already ran whichever upstream validation applies before calling `import_generated_step`.
- Normalizing units or re-orienting imported geometry (Decision 3).
- Installing, vendoring, wrapping, or proxying `cad`, `cad-viewer`, or `step-parts`. All three stay external, user-installed, and directly invoked only by the calling model - never by this repo's Python process (this specifically rules out this repo ever calling `api.step.parts` or starting the `cad-viewer` Node server itself).
- Changing `open_model`, `get_model_info`, `list_features`, or `export_step`'s own contracts.
- Assembly-level `AssemblyHelper`/build123d-joint handoff, or multi-part sourcing in one call - single STEP file per call only.

## Decisions

**1. New tool lives in `src/solidworks_mcp/tools/file_management.py`, alongside `get_model_info`/`list_features`.**
Two of the three adapter calls this tool composes already live there; `open_model` lives in `modeling.py` but is called the same way regardless of which file hosts the new function. Placing it beside its two same-file dependencies keeps the diff smaller and matches this repo's existing grouping.

**2. Composition, not orchestration: call the adapter directly for all three steps, matching the existing pattern.**
`open_model`, `get_model_info`, and `list_features` all call `adapter.<method>()` directly rather than delegating to another `@mcp.tool()`-wrapped function. `import_generated_step` does the same. This is why the change touches zero adapter/COM code - every adapter method it needs already exists and is already exercised by other tools' tests.
*Alternative considered:* a new adapter-level composite method (e.g. `adapter.import_and_describe_step(...)`) that does all three COM operations in one adapter call. Rejected - none of the three underlying operations need to run inside the same COM-executor job (each already round-trips through `_handle_com_operation` independently and safely), so a composite adapter method would only add surface area without a correctness or performance benefit.

**3. STEP import handles units and orientation itself - this tool does not convert or normalize anything.**
STEP (ISO 10303) is self-describing: each file embeds its own unit block and coordinate system. SolidWorks's `OpenDoc6`-based STEP importer (already used by `open_model` for every STEP file today) reads that block and converts internally. Orientation is different: imported geometry keeps whatever coordinate system it was authored in - this tool is a straight import + readback, not a normalizer. Reorientation, if ever needed, is an ordinary follow-up `solidworks-native` operation the caller can request afterward.
*Alternative considered:* pre-parsing the STEP header before import to catch unit/coordinate mismatches early. Rejected - `OpenDoc6` already fails loudly on a malformed STEP file via the existing `open_model` error path; shipping a second STEP header parser for a case SolidWorks's own importer already handles would be pure duplication.

**4. `validation_report` and `part_family` are both opaque, unvalidated passthrough fields - never parsed.**
`import_generated_step(step_path, part_family=None, validation_report=None)`:
- `validation_report: dict[str, Any] | None` - the upstream skill's artifact schema (snapshot paths, `scripts/inspect` facts, or a `step-parts` catalog record) is external and versioned independently of this repo. Echoed back verbatim under `data.upstream_validation`, zero internal parsing.
- `part_family: str | None` - best-supported interpretation (per BRD Section 9, flagged there for explicit maintainer sign-off, not treated as settled fact): a free-text provenance/categorization tag, plausibly mirroring `step-parts`' own `family` facet (their documented example: `family=feetech`) for sourced parts, or a caller-assigned tag like `"bracket"` for generated ones. Echoed back verbatim under `data.part_family`, exactly like `validation_report` - never parsed, never required. If the maintainer's actual intent turns out to differ, changing this costs nothing beyond a rename, since nothing depends on its contents.
If either upstream schema changes, this tool is unaffected - it never inspects either dict/string's contents beyond passing it through.

**5. Fail fast on import failure - do not attempt readback if `open_model` fails.**
If `adapter.open_model(step_path)` returns a non-success result, `import_generated_step` returns that error immediately without calling `get_model_info`/`list_features` - calling readback tools against whatever the previously-active document was would misrepresent success and could return stale, unrelated info.

**6. Partial readback failure: report as a success with the failure surfaced in `data`, not as a top-level error.**
If `open_model` succeeds but `get_model_info` or `list_features` subsequently fails, `import_generated_step` still returns `status: "success"` (the import itself worked - the caller has a live document) with the failing sub-call's error captured under `data.model_info`/`data.features` in place of its normal payload (mirroring the shape those tools already return on their own failure, e.g. `{"status": "error", "message": ...}`), rather than either masking the import's success or discarding it because a secondary readback call had a problem. The caller can always retry `get_model_info`/`list_features` directly - the document is already open and unaffected by a readback failure.
*Alternative considered:* returning a top-level error if any of the three sub-calls fails. Rejected - conflates "the import didn't happen" (genuinely nothing to work with) with "the import happened but a convenience readback call had a hiccup" (a live document exists; failing the whole response would hide that from the caller).

**7. Response shape: nest under `data`, matching CLAUDE.md's stated convention - not the existing tools' own (non-conforming, and mutually different) flat shapes.**
CLAUDE.md states the project convention as `{status, message, execution_time, data}`. Neither composed tool actually follows it today: `open_model`'s response is `{status, message, model: {...}, execution_time}` (no `data` wrapper, model fields under `model`); `get_model_info`'s is `{status, model_info, execution_time}` (no `message`, fields under `model_info`). Both are pre-existing inconsistencies in shipped code, not a second convention to match - and per Decision 2, `import_generated_step` calls `adapter.open_model()`/`adapter.get_model_info()`/`adapter.list_features()` directly rather than the `open_model` *tool* wrapper, so it never inherits either tool's response-building code, only the raw `AdapterResult.data` each adapter call returns. That means this tool is free to shape its own response without reconciling two different existing shapes - it builds fresh from adapter results and follows the *stated* convention:

```python
{
    "status": "success" | "error",
    "message": str,
    "execution_time": float,
    "data": {
        "opened": {...},       # adapter.open_model()'s result.data, as-is (title/type/path/configuration)
        "model_info": {...} | {"status": "error", "message": ...},
        "features": {...} | {"status": "error", "message": ...},
        "upstream_validation": dict | None,  # validation_report, passed through
        "part_family": str | None,           # passed through
    },
}
```
On `open_model` failure (Decision 5), the top-level shape is `{"status": "error", "message": ..., "execution_time": ...}` with no `data` key.

**8. `text-to-cad` branch's `allowed_tools` stays narrow: `["import_generated_step", "get_model_info", "list_features"]`, not the full adapter surface.**
Mirrors `cad-skill-router`'s own design (its Decision 4 reserves the *full* capability set for `solidworks-native` specifically, since that branch has no router in front of it today). The route's `validation_steps` documents both pathways explicitly: (a) generation - run the `cad` skill, get a validated STEP path, call `import_generated_step`; (b) sourcing - run `step-parts`, get a downloaded STEP path, call `import_generated_step` the same way. After a successful import, `validation_steps` also points back at `get_skill_route(family="solidworks-native")` to unlock the full tool surface for further editing.

**9. `solidworks-native` branch documents the preview pathway via `validation_steps`, not a new tool.**
`export_step` already returns an absolute path. The router's `solidworks-native` route gains one more `validation_steps` entry: "to preview SolidWorks-native work in a browser, run `export_step` then hand the returned path to `$cad-viewer` if installed." No code change to `export_step` itself - purely additive router documentation.

**10. Real-SolidWorks test generates its own STEP fixture rather than checking in a binary or depending on either upstream skill.**
The `solidworks_only` test builds a minimal part programmatically (`create_part` → `create_extrusion` → `export_step`) to produce a `.step` file, then feeds that same path into `import_generated_step` - a self-contained round-trip that doesn't require `cad`/`step-parts` to be installed in the test environment and doesn't add a binary CAD fixture to version control, matching this repo's existing `test_live_sw_regression.py` convention of building real-SW fixtures in-test rather than committing them.

## Risks / Trade-offs

- [Risk] This tool cannot verify either upstream skill's validation loop actually ran → [Mitigation] accepted trust boundary: each upstream skill's own workflow enforces its validation before handing off a path at all; this tool's contract is "given a STEP path, import + report," not "gatekeep whether the path is trustworthy."
- [Risk] `part_family`'s meaning (Decision 4) is inferred, not confirmed by the maintainer → [Mitigation] explicitly flagged in the BRD and here rather than silently assumed; costs nothing to rename or drop later since the field is never parsed.
- [Risk] `text-to-cad`/`step-parts` are only turnkey for Claude Code today (plugin-install mechanism); an OpenAI/ChatGPT caller needs another way to produce the STEP file → [Mitigation] already captured in `cad-skill-router`'s design.md Risks; this tool's contract doesn't care how the file was produced.
- [Risk] `step-parts` is a hosted, internet-dependent service outside this repo's control → [Mitigation] this repo's own process never calls it (Non-Goals), so an outage affects only the calling model's sourcing step, never this repo's own tool contract, tests, or CI.
- [Risk] A caller passes a `step_path` that isn't actually STEP (wrong extension, corrupted file) → [Mitigation] no new handling needed - the existing `open_model`/`OpenDoc6` error path, already tested, covers this regardless of which pathway produced the bad file.

## Migration Plan

Not applicable - net-new, additive tool. Rollback is deleting the new tool function and reverting the router's `text-to-cad` branch to its current stub and the `solidworks-native` branch's `validation_steps` to their current content. No data migration.

## Open Questions

- Whether `import_generated_step` is still the best name now that it also covers `step-parts`-sourced (not generated) parts. Deferred - the BRD (Section 11.4) flags the same question; resolving it doesn't change the design or task breakdown, only a possible rename before `tasks.md` execution if the maintainer prefers `import_step_file` or similar.
