## 1. Adapter interface

- [x] 1.1 Add `get_model_geometry_summary()` to `adapters/base.py`, a
      non-abstract method returning an error `AdapterResult` ("not
      implemented by this adapter"), with the payload keys documented (see
      the model-geometry-summary spec); test in `test_base.py`
- [x] 1.2 Forward it in `circuit_breaker.py` and `connection_pool.py`
      following the `list_components` pattern; tests in
      `test_circuit_breaker_geometry_summary.py` and
      `test_connection_pool_geometry_summary.py`

## 2. Mock adapter (own step, per the adapter rule)

- [x] 2.1 Add `self._mates` state, reset wherever `_components` is reset, and
      append to it in mock `add_mate` on success
- [x] 2.2 Implement mock `get_model_geometry_summary`. It returns `null` for
      volume, box and bodies, plus component and mate counts for assemblies,
      and errors for no model or a drawing (design D9)
- [x] 2.3 Tests in `tests/solidworks_mcp/adapters/test_mock_adapter_geometry_summary.py`:
      part, assembly after two `insert_component` + one `add_mate`, no model,
      drawing

## 3. Real adapter (pywin32 mixin in `adapters/solidworks/io.py`)

- [x] 3.1 Implement `get_model_geometry_summary` inside the mixin class (not
      at module scope; see "Adapter wiring traps"). Route it through
      `_handle_com_operation`, with no `ForceRebuild3` and no `ClearSelection2`
- [x] 3.2 Part path:
      - `GetBodies2(0, False)` for the solid-body count;
      - per-body `GetExtremePoint` box, falling back to `GetPartBox(True)`,
        with `bounding_box_method` set to match;
      - volume via `CreateMassProperty()`.
      Units are metres → mm. Flag `IPartDoc`/`IBody2` (design D3, D4)
- [x] 3.3 Assembly path:
      - `GetBox(0)` for the box;
      - `_component_names` for the component count;
      - mate count by walking the `MateGroup` sub-features (flagged, skipping
        suppressed ones, recursing one level into folders);
      - volume via `CreateMassProperty()`
- [x] 3.4 Unit tests with fake COM objects in
      `tests/solidworks_mcp/adapters/solidworks/test_io_geometry_summary.py`:
      - extreme-point success;
      - extreme-point failure → part-box fallback;
      - no bodies;
      - assembly with mates in a folder;
      - suppressed mate skipped;
      - drawing / no model errors;
      - asserts that `ForceRebuild3` and `ClearSelection2` are never called

## 4. `verify_model` tool (`tools/analysis.py`)

- [x] 4.1 `VerifyModelInput` schema (plain BaseModel with `extra="forbid"`, not
      CompatInput: a misspelt expectation must error, not be silently skipped):
      - optional expectations: `mass_kg`, `volume_mm3`, `bounding_box_mm`
        (3 floats), `feature_count`, `solid_body_count`, `component_count`,
        `mate_count`, `no_interference`;
      - `relative_tolerance` (0.01) and `length_tolerance_mm` (0.1), both ≥ 0
- [x] 4.2 Pure helpers:
      - `_count_modelling_features(descriptors)`, the D5 filter, returning
        the names;
      - `_relative_check` / `_length_check` / `_exact_check` /
        `_boolean_check`, each returning a check dict;
      - `_verdict(checks)` (pass / fail / inconclusive / report_only)
- [x] 4.3 Tool body:
      1. require the summary capability;
      2. read the summary;
      3. reject a drawing or an assembly-only expectation on a part with
         `InvalidInputError`;
      4. call `get_mass_properties`, `list_features` and `check_interference`
         only when their expectation is given;
      5. build `checks`, `measured`, `verdict` and `message` (design D6).
      No `try/except`
- [x] 4.4 Docstring written for agents: when to call it, units, how to widen
      tolerances for fillets and for `assembly_box`, and the meaning of
      `passed: null`
- [x] 4.5 Tests in `tests/solidworks_mcp/tools/test_analysis_verify_model.py`,
      covering every scenario in the model-verification spec:
      - all pass; volume fail;
      - report_only; inconclusive interference;
      - bbox per-axis; counted features listed;
      - feature filter (default planes by position, sketches, folders);
      - mate count on a part → error; negative tolerance → error;
        drawing → error;
      - zero-expected volume (an expected 0 needs exactly 0; the design's
        length³ fallback was dropped as needless)

## 5. Measured change on solid features (`tools/modeling.py`)

- [x] 5.1 Helper `_measured_change(before, after)` building the block from
      two `AdapterResult`s. It returns `None` when the "before" read errored
      (adapter lacks the read) and `null` fields plus a `note` when values are
      not determinable
- [x] 5.2 Wire it into `create_extrusion`, `create_revolve` and
      `create_cut_extrude`: summary before the adapter call, summary after
      success, `measured_change` key added, `warning` when the volume delta
      is exactly 0. Existing keys unchanged
- [x] 5.3 Tests in `tests/solidworks_mcp/tools/test_modeling_measured_change.py`:
      - extrude delta (patched summary);
      - cut with zero delta → warning;
      - adapter without the read → no key and the reply otherwise identical;
      - mock → nulls and a note;
      - the after-read failing does not fail the tool
- [x] 5.4 Re-run `tests/solidworks_mcp/tools/test_modeling.py` unchanged, to
      prove existing reply keys are untouched

## 6. Docs and counts

- [x] 6.1 Run `check_tool_docs_consistency.py --fix` (151 → 152) and add
      `verify_model` to the analysis tools reference page
- [x] 6.2 Document `measured_change` on the modelling tools page, and add
      `verify_model` as the closing step in the agent workflow docs under
      `docs/agents/`
- [ ] 6.3 Add a COM pitfall entry for whatever the live probe in 7.1 finds
      about `GetExtremePoint` out-params (or note that it worked as written)
- [x] 6.4 CHANGELOG `Unreleased → Added` entries for `verify_model` and
      `measured_change`
- [x] 6.5 Run `ruff check src tests`, the mock-only test suite and
      `mkdocs build --strict`; coverage on the new code is 100 % without
      pragmas

## 7. Live verification (only after the maintainer says go; `SW_TEST_PACE_SECONDS=4`)

- [ ] 7.1 Non-destructive probe on a new scratch part: block 100 × 50 × 10.
      Check the extreme-point box against the part box, volume = 50000, and
      body count 1
- [ ] 7.2 `tests/live/test_live_sw_verify_model.py`:
      - block part → `verify_model` passes with exact expectations and fails
        with a wrong volume;
      - Ø20 × 40 revolve → box within 0.1 mm via extreme points;
      - edge selected → summary read leaves the selection count unchanged
        (design risk 1);
      - two-part assembly with two mates → component and mate counts and the
        interference check;
      - extrude and cut → `measured_change` deltas match hand calculations
- [ ] 7.3 Live demo of `verify_model` and `measured_change` to the maintainer
      (live-demo-signoff) before the PR is merged
- [ ] 7.4 Open the PR closing #173; link it from the bracket demo issue (#147)
