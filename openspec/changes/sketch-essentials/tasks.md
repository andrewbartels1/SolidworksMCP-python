## 1. Adapter (COM) in `adapters/solidworks/sketch.py`

- [x] 1.1 `_corner_points` (the open sketch's point within 0.01 mm of each sketch-mm corner, all found before any change) and `_to_model_space` (sketch mm to model metres, the inverse of `ModelToSketchTransform`)
- [x] 1.2 `_add_sketch_fillet_impl` and `_add_sketch_chamfer_impl`: every corner found before any change, then one `CreateFillet` (keep constrained corners) or `CreateChamfer` per corner; one registered id per corner
- [x] 1.3 `_add_slot_impl`: `CreateSketchSlot`, straight (line, centre-to-centre) and arc (centre, start, end, counter-clockwise); registered id; area
- [x] 1.4 `_sketch_trim_impl` and `_sketch_extend_impl`: point to model space, select the segment there (null callout), `SketchTrim(closest)` / `SketchExtend`; segment counts before and after; nothing selected or `False` is an error
- [x] 1.5 `_set_construction_geometry_impl`: ids checked first, `ConstructionGeometry` set on every segment and read back
- [x] 1.6 `_add_arc_impl` takes `kind` (`Create3PointArc`, `CreateTangentArc` forward) and `_add_rectangle_impl` takes `from_center` (`CreateCenterRectangle`), both defaulting to today's call
- [x] 1.7 Mixin methods for each; unit tests in `test_sketch.py` with fake COM objects (success, each failure, nothing changed on failure)

## 2. Adapter wrappers and mock

- [x] 2.1 `base.py`, `circuit_breaker.py`, `connection_pool.py`: the six new methods and the new `add_arc` / `add_rectangle` arguments; tests beside each
- [x] 2.2 `mock_adapter.py`: the six methods (plausible ids, areas and counts; the same input errors) and the new arguments; tests

## 3. Tools in `tools/sketching.py`

- [x] 3.1 Inputs: `AddSketchFilletInput`, `AddSketchChamferInput` (`distance2` or `angle`, not both), `AddSlotInput` (points by `kind`), `SketchPointInput` (trim, extend), `SetConstructionGeometryInput`; `AddArcInput` `kind` and `through_x`/`through_y`; `AddRectangleInput` `from_center`
- [x] 3.2 The six tools, descriptions to the standard (Use it for / Needs / Changes / Returns), replies as in the specs
- [x] 3.3 `construction` on `add_line`, `add_circle`, `add_rectangle` calls `set_construction_geometry` on the new id
- [x] 3.4 `tool_hints.py`, `support_levels.py` (stable after the live demo; beta until then), `test_all_endpoints_harness.py` entries; tests in `test_sketching.py`

## 4. Docs

- [x] 4.1 Catalog `sketching.md`: the six tools, and `add_arc` `kind` / `add_rectangle` `from_center`; tool counts to 151 (README, docs index, catalog index, tools overview)
- [x] 4.2 Progress files and `llms.txt` regenerated; CHANGELOG
- [x] 4.3 Unit suite at 100% coverage, ruff, mypy, mkdocs strict, link check

## 5. Live demo and sign-off

- [x] 5.1 `tests/live/test_live_sw_sketch_essentials.py`: a slotted bracket plate. A centre rectangle, two corners filleted and two chamfered, extruded 8 mm; straight and arc slots, a keyhole (lines extended to a circle, the inner arc trimmed), and a stadium window (tangent and three-point arcs) cut through, with a construction line in the cut sketch; the volume checked against the hand calculation after each step, and one refused call (a corner that isn't there)
- [ ] 5.2 The user runs the demo; fix anything it finds; record the GIF; demos page section and README tile if the user wants one
- [ ] 5.3 Promote the six tools to stable; commit; ask before pushing
