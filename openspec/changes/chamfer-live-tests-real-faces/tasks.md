## 1. Shared coupon helper

- [x] 1.1 New `tests/live/coupon.py`: the coupon builder (moved from `test_live_sw_add_chamfer_tool.py`), its bounding box from `get_model_geometry_summary()`, the `hole_face`, `side_face`, `opposite_edge` and `inside` points derived from the box (design decision 1), the exact volume formulas with the mitred-corner term (decision 2), and the `add_chamfer_tool` and `feature_names` helpers
- [x] 1.2 `tests/live/test_live_sw_api_lookup.py` uses the helper instead of its own `_hole_face` and imports, and checks the exact volume

## 2. Chamfer and fillet tests

- [x] 2.1 `test_live_sw_add_chamfer_tool.py` holds only calls that must create a feature, each checked against its exact volume within 0.001 mm³: the hole face, a side face, the hole face plus an opposite-face edge, and a fillet on one edge
- [x] 2.2 New `test_live_sw_edge_pick_refusals.py` holds only calls that must be refused (a bad name, a good entry with a bad one, a point inside the block); each checks the error and that the part is unchanged, and labels its evidence "Refused, as it should be"
- [x] 2.3 Each test prints its box, points, and measured, exact and difference volumes with `evidence(...)`

## 3. Code and docstrings

- [x] 3.1 Rewrite the test module docstring (design decision 4)
- [x] 3.2 Correct `_parse_edge_spec`'s docstring in `src/solidworks_mcp/adapters/solidworks/features.py`
- [x] 3.3 An edge or face entry that selects nothing raises `LookupError` in `_add_chamfer_impl` and `_add_fillet_impl`, so it is logged as one warning line instead of a traceback (decision 5)
- [x] 3.4 `SW_DEMO_TRACE` / `live_demo.ps1 -Trace` prints each SolidWorks call with a timestamp, to match SolidWorks' error sound to its call (decision 6)

## 4. Verify

- [x] 4.1 ruff, the non-live suite at 100% coverage, `openspec validate --strict`
- [x] 4.2 Live run of both test files and the API lookup chamfer demo with `live_demo.ps1 -Trace`, with the user's permission; find what makes SolidWorks bonk
- [ ] 4.3 PR closing #199
