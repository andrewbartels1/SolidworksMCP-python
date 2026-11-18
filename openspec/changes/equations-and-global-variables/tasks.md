## 1. Adapter

- [x] 1.1 Adapter interface `list_equations`, `set_equation`, `delete_equation` through `base.py`, `circuit_breaker.py`, `connection_pool.py`; tests
- [x] 1.2 Real adapter mixin `adapters/solidworks/equations.py`: walk, name parse, dimension check, `Add2`, the `Equation` property put and `SetEquationAndConfigurationOption(..., 1, None)` per configuration (design decision 4) with read-back and restore, `Delete`, `EvaluateAll` + rebuild; tests with a fake that refuses configuration-name arrays as SolidWorks does
- [x] 1.3 Mock adapter: equation list, simple values, refusal of an unknown global variable; tests

## 2. Tools

- [x] 2.1 `tools/equations.py`: inputs (name and expression checks, `configurations`), the three tools, registration; tests
- [x] 2.2 `equation_refused` classifier rule; hints, support levels, toolsets; tool count 143; the `delete_` meaning in the description standard

## 3. Docs

- [x] 3.1 Catalog page; the agent skill's note on making a part parametric; CHANGELOG; queue row 29; progress bars regenerated
- [x] 3.2 Full mock suite at 100% coverage, ruff, mypy, `mkdocs build --strict`

## 4. Live

- [x] 4.1 Live probes of `IEquationMgr` (2026-11-17/18) and the fixes they led to (design decision 4); `Value` is in the document's units
- [x] 4.2 Wrench demo `tests/live/test_live_sw_equations_wrench.py`: 13 mm combination wrench, 19 equations, `Size` = 19mm regrows it, 8 mm in its own configuration, a bad expression refused; passed live and recorded 2026-11-18. Needed `create_cut_extrude` mid-plane for Blind `both_directions`, a polygon `diameter` dimension and `add_polygon` `angle`; tests for each
- [x] 4.3 Demos page section, README tile, catalog notes, CHANGELOG
- [ ] 4.5 The wrench closer to the user's reference (review 2026-11-18): the jaw bottom curved by an ellipse cut (`add_ellipse` `angle`; `add_sketch_dimension` `major_axis` / `minor_axis` on an ellipse), neck fillets on both heads sized by Size, material 1.8159 (51CrV4) chrome-vanadium steel; tests for each tool change
- [ ] 4.7 `add_sketch_text` (design: Text on the wrench's handle): adapter (`InsertSketchText` at a point, `CharHeight`, `center_at` by measuring its edges), `base`/`circuit_breaker`/`connection_pool`/mock, the tool, hints, support level, toolset, catalog, tool count 144; tests. The wrench debosses "solidworksmcp-python" and its size (`$PRP:` linked to a Size dimension) into both faces of the handle, centred at every size (cut on a spare block, patterned onto the handle by `"Size" * 6.51 + 190mm`), and each evidence line shows the equation set and the size before and after
- [ ] 4.6 Once the user approves the wrench: re-record, then the demos page section, README tile, catalog notes and CHANGELOG
- [ ] 4.4 The user runs `tests/live/test_live_sw_equations.py` (block tests) and approves the demo; archive after
