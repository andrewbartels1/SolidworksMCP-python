## 1. Shared pieces

- [x] 1.1 `face_selection.py`: pick a face or edge by point with a mark and append, and report whether it is flat, circular or neither; tests
- [x] 1.2 Feature tools' shared success rule: the feature exists and the volume moved, else delete the feature and fail; tests

## 2. Linear pattern

- [x] 2.1 `PatternLinearInput`, `pattern_linear` tool, hints, level; tests
- [x] 2.2 Adapter interface `pattern_linear` in `base.py`, `circuit_breaker.py`, `connection_pool.py`; tests
- [x] 2.3 Real adapter: select features and directions, `FeatureLinearPattern5`, volume check; tests
- [x] 2.4 Mock adapter: a pattern's volume change from count and the seed's volume; tests

## 3. Shell, draft, rib

- [x] 3.1 Inputs and tools `create_shell`, `add_draft`, `create_rib`; the one-of rule for the neutral face; tests
- [x] 3.2 Adapter interface for the three, through every layer; tests
- [x] 3.3 Real adapter: `InsertFeatureShell`, `InsertMultiFaceDraft`, `InsertRib`, with the picks and marks; tests
- [x] 3.4 Mock adapter: the open-box shell volume, a draft's volume change, a rib's volume; tests

## 4. Holes and threads

- [x] 4.1 `CreateHoleInput` with the hole type, standard, size table and end condition; `invalid_input` for a size outside the table and a blind hole with no depth; tests
- [x] 4.2 `AddCosmeticThreadInput` and tool; tests
- [x] 4.3 Adapter interface for both, through every layer; tests
- [x] 4.4 Real adapter: `HoleWizard5` from the code table (to be confirmed by 6.1), `InsertCosmeticThread3` on a circular edge; tests
- [x] 4.5 Mock adapter: a hole's volume from its size and depth; a thread leaves the volume; tests

## 5. Convert entities

- [x] 5.1 `SketchConvertEntitiesInput` (one of `edge_points`, `face_point`; `construction`) and tool; tests
- [x] 5.2 Adapter interface through every layer; tests
- [x] 5.3 Real adapter: picks, `SketchUseEdge3`, new segments registered, construction set; tests
- [x] 5.4 Mock adapter: a face's four edges become four registered lines; tests

## 6. Live bundle (one set, run together, then fixes one by one)

- [x] 6.1 Hole Wizard diagnostic (passed 2026-11-16): one hole of each type for ISO and ANSI, recording which codes SolidWorks honoured
- [x] 6.2 (all passed 2026-11-16) Live tests for each tool's spec scenarios: the 3 × 2 grid, the open box, drafted sides, a rib in the box, an M6 counterbore and M5 tapped hole, an M10 thread, a converted face outline cut through; each failure case
- [x] 6.3 Hand the user the bundle; fix each failure afterwards, one at a time; move `create_hole` to stable when the diagnostic and its tests pass

## 7. Docs and finish

- [x] 7.1 Tool catalog pages, the agent skill's notes (one hole per call then pattern; thread after hole; convert then cut), `docs/planning/solidworks-api-coverage.md` section 3.7
- [x] 7.2 CHANGELOG (Added), progress bars regenerated
- [x] 7.3 Full mock suite at 100% coverage, ruff, `mkdocs build --strict`
- [x] 7.4 Sign-off, PR (no attribution) closing #105, archive, the queue updated

## 8. After the live demos (2026-11-15)

- [x] 8.1 `create_hole` `positions`: the points added to the hole's position sketch (design decision 7), through base, circuit breaker, connection pool and the real adapter, with tests
- [x] 8.2 The mock adapter's `create_hole` takes `positions` (one hole's volume per point), with tests
- [x] 8.3 A simple hole through all falls back to blind at the part box's diagonal (decision 8), with tests
- [x] 8.4 The tool input and description (`positions`, `hole_count`, `end_condition_used`), the skill's workflow note, the catalog page
- [x] 8.5 Live: `test_holes_at_several_points` (now a plate: each hole type from points, a mirror, a ring, a refusal on purpose; the docs demo) and the pattern demo rerun, both passed 2026-11-16
