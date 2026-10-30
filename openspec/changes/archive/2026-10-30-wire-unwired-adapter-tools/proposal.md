## Why

Issue #106: three adapter capabilities that already work — `list_drawing_views`,
`rebuild_model` and `select_feature` — have no `@mcp.tool()` wrapper, so no MCP
client can reach them. The local-LLM prompt catalog in
`ui/services/llm_service.py` already advertises `select_feature`, so agents on
that path call a tool that does not exist.

A live check on SW 3DEXPERIENCE R2026x (2026-10-13) found that `select_feature`
is also broken: it returns `status=success` with `data.selected == False` for
an existing `Boss-Extrude1`, so it fails without saying so. `rebuild_model`
returns only pass/fail, which gives an LLM nothing to act on. And there is no
way to say "select all the (circular) edges on the top face" so that
`add_chamfer`/`add_fillet` can act on that set.

User decisions (2026-10-13):
1. An unselectable name is an ERROR, never a quiet success.
2. A rebuild must report exactly what is wrong — per feature, with a fix
   hint — so the LLM can repair the model.
3. Selection is single by default and multi-select on request, including
   every edge of a face, chosen by a point, a side or a plane.

## What Changes

- **New MCP tools** (134 → 138):
  - `list_drawing_views` (`tools/drawing.py`): view names on the active
    drawing; ERROR when the active document is not a drawing.
  - `rebuild_model` (`tools/modeling.py`): force a rebuild and return
    per-feature diagnostics.
  - `select_feature` (`tools/modeling.py`): select a named feature, sketch,
    plane or component. Replaces the current selection by default; with
    `append: true` it adds to it.
  - `select_face_edges` (`tools/modeling.py`): multi-select every edge
    bounding one face. The face is chosen by `point` (mm), `side`
    (`+X…-Z` / `top|bottom|front|back|right|left`) or `plane` (reference
    plane name). An optional `edge_type` filter (`all|linear|circular`)
    narrows the edges. The tool returns a description of each selected
    edge. Designed to chain into `add_chamfer`/`add_fillet` with empty
    `edge_names`, which act on the live selection.
- **Fix `select_feature` failing silently**:
  - Add a `FeatureByName` + `IFeature::Select2` strategy first. Suppress and
    rename already use this path successfully.
  - Pass an explicit `VT_DISPATCH` null as the `SelectByID2` callout instead
    of `None` (CLAUDE.md pitfall #11).
- **BREAKING (internal only)**: when nothing could be selected,
  `select_feature` returns `AdapterResultStatus.ERROR` instead of SUCCESS
  with `selected: False`. Its only caller, `preview_service.py`, already
  treats a failed result as "not selected".
- **Rebuild diagnostics**: `rebuild_model` returns `errors` — one entry per
  failing feature with `feature`, `type`, `code`, `code_name`, `severity`
  (error/warning), `description`, `parents` and `hint` — plus
  `error_count` and `warning_count`. Status rules:
  - Any remaining error → ERROR, with the full list in `data`.
  - Warnings only → SUCCESS, with the warnings listed.
  - Error codes come from SolidWorks' constants type library (`swconst.tlb`),
    not hand-typed.
- **Full adapter chain**: `rebuild_model`, `select_feature` and
  `select_face_edges` are declared in `base.py` with "not implemented"
  defaults, and passed through in `circuit_breaker.py` and
  `connection_pool.py`. Today `rebuild_model` and `select_feature` exist
  only on the pywin32 mixins and the mock, so calling them through the
  wrapped adapter would raise `AttributeError`.
- **Mock adapter parity** for all four.
- The `mcp_tool_catalog` string in `llm_service.py` is checked against the
  real tool set.
- Docs: tool catalog pages, `docs/planning/solidworks-api-coverage.md`,
  tool counts, and new COM pitfalls if any turn up.

## Capabilities

### New Capabilities
- `tools/drawing-view-listing`: list the views on the active drawing.
- `tools/model-rebuild`: force a rebuild and report per-feature rebuild
  errors and warnings, each with a fix hint.
- `tools/feature-selection`: select named features, single or appended, and
  multi-select every edge of a face given by a point, side or plane. Errors,
  never false successes.

### Modified Capabilities
<!-- none: openspec/specs/ has no main specs yet -->

## Impact

- **Touches COM/adapter code**:
  - `adapters/pywin32_adapter.py` (`FeatureSelector`)
  - `adapters/solidworks/selection.py`
  - `adapters/solidworks/io.py` (`rebuild_model` diagnostics)
  - `adapters/solidworks/features.py`: reuse of `_select_feature_by_name`
    and `_select_edge_by_coord`; face-resolution helpers live beside them
  - `adapters/base.py`, `adapters/circuit_breaker.py`,
    `adapters/connection_pool.py`, `adapters/mock_adapter.py`
  - Risk: all COM work stays inside `_handle_com_operation` on the
    ComExecutor thread. New dispatches (`IFace2`, `IEdge`, `ICurve`,
    `IFeature`, `IModelDocExtension`) are method-flagged. The out-parameter
    APIs used for rebuild diagnostics are a late-binding risk; the first
    task checks them live.
- **Tools**: `tools/drawing.py`, `tools/modeling.py`, with new strict inputs
  `SelectFeatureInput`, `SelectFaceEdgesInput` and `RebuildModelInput`.
- **UI**: no behavior change in `preview_service.py`. The catalog string in
  `llm_service.py` is verified.
- **Tests**: unit tests for each tool and each adapter layer. The existing
  SUCCESS-with-`selected: False` tests are updated to expect ERROR. The
  live test `tests/live/test_live_sw_issue106_tools.py` is the sign-off
  evidence.
