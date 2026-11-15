## 1. Feature order

- [x] 1.1 Real adapter: `list_features` sorts each document's rows by `position` (both passes numbered by tree place); tests where the forward walk stops early and the reverse pass finds the rest
- [x] 1.2 Mock adapter: its rows stay in tree order, with a test that `position` rises
- [x] 1.3 `verify_model`: sort rows by `position` before skipping the three default planes; tests with rows newest first and with `Plane1`

## 2. Dimension listing

- [x] 2.1 Real adapter: `list_model_dimensions` uses `list_features`' walk (shared), skips folders, keeps each `full_name` once with `feature` from the `@` suffix; tests for no name, a name, a plane offset seen from a cut, and a missing feature
- [x] 2.2 Mock adapter: same de-duplication and `feature` rule; tests
- [x] 2.3 Tool description: say each dimension is listed once, under its own feature

## 3. STL export

- [x] 3.1 Real adapter: `SaveAs2` with its eight arguments (by-reference `Errors` and `Warnings`, `VT_DISPATCH` null when there is no export data); remove the second wrong call; `SaveAs3` fallback reports that the options weren't applied; tests for each path
- [x] 3.2 Mock adapter and tool: the fallback's note reaches the reply's `warning`; tests

## 4. Sketch on a face

- [x] 4.1 `CreateSketchInput`: `plane` optional, `face_point` added, exactly one of them; tests for both, neither and a short point
- [x] 4.2 Adapter interface: `create_sketch(plane, face_point=None)` in `base.py`, `circuit_breaker.py` and `connection_pool.py`; tests
- [x] 4.3 Real adapter: select the face at the point with `_select_face_at_point` (flat check included), insert the sketch; a `face_point ... is not on a flat face` error, classified `invalid_input`, for no face or a curved face; tests
- [x] 4.4 Mock adapter: a point on its block's top face opens a sketch; other points are refused; tests
- [x] 4.5 Docs: the sketching catalog page and the skill's note on sketching on a face

## 5. The monitor stand demo

- [x] 5.1 `scripts/demo_monitor_stand.py`: pocket sketched on the top face with `face_point`; `create_reference_plane` drops out; camera to isometric after each cut and the fillet, behind a flag
- [x] 5.2 Its live test: the volume matches 901 769 mm³ at the defaults, and the pocket follows a changed height after a rebuild
- [x] 5.3 `docs/demos.md#monitor-stand`: the call list and count, and drop "one thing can't be matched"

## 6. Live bundle (one set, run together, then fixes one by one)

- [x] 6.1 Live tests (written in `test_live_sw_monitor_stand_follow_ups.py` and `test_live_sw_monitor_stand_demo.py`; run live 2026-11-14, all five pass): feature order and `verify_model` on a part with `Plane1`; the dimension diagnostic (old walk vs new, counts) and the full listing on the stand; STL export path and file size; `create_sketch` on a face, the follow-the-height rebuild, a point in the air and a point on a fillet
- [x] 6.2 Hand the user the bundle; fix each failure afterwards, one at a time (two failed: `SaveAs2` takes eight arguments, `Warnings` too; the face test read a name `exit_sketch` doesn't return. Both fixed and passed on the re-run)
- [x] 6.3 Re-record the monitor stand GIF with `SW_DEMO_RECORD`

## 7. Finish

- [x] 7.1 CHANGELOG (Unreleased): Fixed (feature order, `verify_model`, dimension listing, STL), Added (`create_sketch` `face_point`)
- [x] 7.2 Full mock suite at 100% coverage, ruff, `mkdocs build --strict`, progress files regenerated
- [x] 7.3 Sign-off, PR (no attribution), archive, and the queue updated
