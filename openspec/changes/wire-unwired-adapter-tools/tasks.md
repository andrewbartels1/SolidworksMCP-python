## 1. Live probes (before any fix): record findings in design.md Context

- [x] 1.1 `select_feature` probe on a scratch box part. For `Boss-Extrude1`, `Sketch1` and `Front Plane`, record which `FeatureSelector` strategy fails and its swallowed exception: `SelectByID2` with a `None` callout vs `_null_callout()`, and the tree walk's `FirstFeature`/`Select2`
- [x] 1.2 Rebuild-diagnostics probe. Build a part whose fillet loses its edge after a dimension change. Try `GetWhatsWrong`, `GetErrorCode2` (late-bound, then a targeted early-bound wrapper) and `GetErrorCode` in that order. Record which ones return usable data, and that `GetParents` returns names
- [x] 1.3 Face/edge probe on a box with a through-hole. Check that these work late-bound:
  - `GetBodies2` → `GetFaces` → `IGetSurface().IsPlane()` and `Normal`
  - `GetEdges` → `GetCurve().IsCircle()` and `CircleParams`
  - the `IRefPlane` transform
  - `IEntity.Select4`

  Record the method-vs-property findings

## 2. Feature-error enum table

- [x] 2.1 Script `scripts/gen_sw_feature_errors.py`: load `swconst.tlb` and emit `src/solidworks_mcp/adapters/sw_feature_errors.py` (code → enum-member name). Commit the generated file with a header saying how to regenerate it
- [x] 2.2 Add curated `hint` and `description` entries for the common codes (missing reference, sketch profile, invalid geometry, pattern seed), with a generic fallback. Unit tests: every curated key exists in the generated table; an unknown code gets the fallback

## 3. Adapter interface: base + wrappers

- [x] 3.1 `base.py`: `select_feature(feature_name, append=False)`, `select_face_edges(point=None, side=None, plane=None, edge_type="all", append=False)` and `rebuild_model(top_level_only=False)` as "not implemented" ERROR defaults, with docstrings giving the payload contracts
- [x] 3.2 `circuit_breaker.py` pass-throughs for all three, using per-operation buckets
- [x] 3.3 `connection_pool.py` pass-throughs for all three
- [x] 3.4 Tests: base defaults return ERROR; both wrappers delegate the call and every argument

## 4. Real adapter: select_feature fix + append

- [x] 4.1 Generalize `features._select_feature_by_name` to take `append`, keeping the existing suppress/rename callers unchanged at `append=False`
- [x] 4.2 Add `FeatureSelector.try_select_by_feature_name` as the first strategy; thread `append` through every strategy
- [x] 4.3 Use `_null_callout()` in `try_select_by_extension` (pitfall #11)
- [x] 4.4 Fix whatever 1.1 shows is wrong in the tree-walk strategy (method flagging), if anything
- [x] 4.5 In `selection.py`, map an unselected payload to an ERROR naming the feature, and add `selection_count`
- [x] 4.6 Unit tests:
  - the new strategy runs first and short-circuits
  - the callout is a VARIANT
  - `append` is forwarded
  - not-found returns ERROR
  - update `test_select_feature_returns_unselected_when_all_strategies_fail` to expect ERROR
- [x] 4.7 Confirm `preview_service.py` behavior is unchanged with ERROR-on-not-found; adjust its tests if they relied on SUCCESS+False

## 5. Mock adapter: select_feature parity

- [x] 5.1 Mock `select_feature`: tracked names only, a tracked selection list for `append`/`selection_count`, and an ERROR naming the feature otherwise
- [x] 5.2 Mock tests for: known name, unknown name, append count, no active model. Update the `test_coverage_push_final.py` cases that select untracked names

## 6. Real adapter: select_face_edges

- [x] 6.1 New `adapters/solidworks/face_selection.py` with the face resolver (`point`/`side`/`plane`) per design decision 4, using the flagging found in 1.3
- [x] 6.2 Edge collector with an `edge_type` filter and edge descriptions. Extract the edge-description code shared with `get_selected_entities` into one helper and use it from both
- [x] 6.3 Selector: `ClearSelection2` unless `append`, `IEntity.Select4` per edge, then read `selection_count` back and ERROR on a mismatch
- [x] 6.4 `SolidWorksSelectionMixin.select_face_edges` wiring through `_handle_com_operation`, with a part-document guard
- [x] 6.5 Unit tests with fake COM objects covering:
  - each resolver mode, side-alias mapping, and the tie-break by area
  - the `plane` multi-face case
  - the edge filter
  - the no-face, no-matching-edges and non-part errors
  - the select-count mismatch

## 7. Mock adapter: select_face_edges parity

- [x] 7.1 Mock `select_face_edges`: canned box faces for the six sides, circular edges only when a hole/cut exists, errors for unknown plane, off-body point or no edges of the requested type
- [x] 7.2 Mock tests for each path

## 8. Real adapter: rebuild_model diagnostics

- [x] 8.1 `io.py` `rebuild_model(top_level_only=False)`:
  - `ForceRebuild3(top_level_only)`; False → ERROR
  - collect diagnostics through the source chosen in 1.2
  - build the entries (`feature`, `type`, `code`, `code_name`, `severity`, `description`, `parents`, `hint`), skipping suppressed features
  - return ERROR-with-data when errors remain, SUCCESS for warnings only
- [x] 8.2 Unit tests with fake COM objects: clean rebuild, one error, warnings only, unknown code → fallback hint, a parents list, suppressed feature skipped, rebuild failure, no active model

## 9. Mock adapter: rebuild_model parity

- [x] 9.1 Mock `rebuild_model(top_level_only=False)`: clean result by default, ERROR with no model, plus a test hook that injects a failing feature
- [x] 9.2 Mock tests for clean, injected error, injected warning and no model

## 10. MCP tools, catalog and docs

- [x] 10.1 `tools/drawing.py`: `list_drawing_views` tool (no input) returning `views`, `count`, `message` and `execution_time`; errors returned, not raised
- [x] 10.2 `tools/modeling.py`: `RebuildModelInput` + `rebuild_model`. Pass `data` through on both success and error; the message names the failing features or mentions warnings
- [x] 10.3 `tools/modeling.py`: `SelectFeatureInput` + `select_feature`
- [x] 10.4 `tools/modeling.py`: `SelectFaceEdgesInput` (exactly-one validator, side tokens, `edge_type` Literal) + `select_face_edges`. The docstring shows the chain into `add_chamfer(edge_names=[])` and warns that selection is live UI state
- [x] 10.5 Tool tests in `tests/solidworks_mcp/tools/` for every spec scenario reachable with the mock
- [x] 10.6 Update tool-count and registration tests (134 → 138) and the all-endpoints harness expectations
- [x] 10.7 Check the `mcp_tool_catalog` string in `llm_service.py` against the registered tools; fix any advertised-but-missing names and add the new tools
- [x] 10.8 Docs:
  - `docs/user-guide/tool-catalog/` pages, `tools-overview.md` and the `docs/index.md` counts
  - `docs/planning/solidworks-api-coverage.md`, marking GetSelectedObject*/selection and rebuild coverage
  - new pitfalls from 1.x added to `docs/agents/com-api-pitfalls.md`
- [x] 10.9 `dev-docs-build` + `dev-docs-strict` are clean

## 11. Quality gates

- [x] 11.1 `dev-lint` clean on touched files (the 14 existing ruff findings are untouched)
- [x] 11.2 `dev-test` passes; new code paths are ≥ 80% covered (check with a `--cov` report on the touched modules)

## 12. Live verification and per-tool sign-off (required before PR)

- [x] 12.1 `tests/live/test_live_sw_issue106_tools.py` covers:
  - `select_feature`: `Boss-Extrude1`, `Sketch1` and a qualified name, each checked via `get_selected_entities`/`ISelectionMgr`; `append` gives a count of 2; unknown name → ERROR
  - `select_face_edges`:
    - box + through-hole, `side="top", edge_type="circular"` → only the rim, with the correct radius
    - `point` on a plain face → 4 edges
    - `plane="Front Plane"`
    - the chain `select_face_edges` → `add_chamfer(edge_names=[])`, checking the volume delta matches a rim chamfer
    - no-circular-edges → ERROR
  - `rebuild_model`: clean part → no errors; fillet-loses-edge → ERROR whose entry names the fillet, with `code_name`, `parents` and `hint`
  - `list_drawing_views`: a generated drawing lists its views; a part → ERROR
- [x] 12.2 Run the new live test plus `test_live_sw_wave3.py`, `test_live_sw_regression.py` and the add_chamfer live test against real SolidWorks. Capture the printed evidence
- [ ] 12.3 Present the live evidence to the user **one tool at a time** for sign-off. Do not open the PR or start #101 until the user approves every tool
- [ ] 12.4 Open the PR (closes #106) with the live evidence in the body
