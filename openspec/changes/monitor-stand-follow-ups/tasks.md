## 1. Feature order

- [ ] 1.1 Real adapter: `list_features` sorts each document's rows by `position` (both passes numbered by tree place); tests where the forward walk stops early and the reverse pass finds the rest
- [ ] 1.2 Mock adapter: its rows stay in tree order, with a test that `position` rises
- [ ] 1.3 `verify_model`: sort rows by `position` before skipping the three default planes; tests with rows newest first and with `Plane1`

## 2. Dimension listing

- [ ] 2.1 Real adapter: `list_model_dimensions` uses `list_features`' walk (shared), skips folders, keeps each `full_name` once with `feature` from the `@` suffix; tests for no name, a name, a plane offset seen from a cut, and a missing feature
- [ ] 2.2 Mock adapter: same de-duplication and `feature` rule; tests
- [ ] 2.3 Tool description: say each dimension is listed once, under its own feature

## 3. STL export

- [ ] 3.1 Real adapter: `SaveAs2` with its seven arguments (by-reference `Errors`, `VT_DISPATCH` null when there is no export data); remove the second wrong call; `SaveAs3` fallback reports that the options weren't applied; tests for each path
- [ ] 3.2 Mock adapter and tool: the fallback's note reaches the reply's `warning`; tests

## 4. Sketch on a face

- [ ] 4.1 `CreateSketchInput`: `plane` optional, `face_point` added, exactly one of them; tests for both, neither and a short point
- [ ] 4.2 Adapter interface: `create_sketch(plane, face_point=None)` in `base.py`, `circuit_breaker.py` and `connection_pool.py`; tests
- [ ] 4.3 Real adapter: rebuild, select the face at the point, check it is flat, insert the sketch; `InvalidInputError` for no face or a curved face; tests
- [ ] 4.4 Mock adapter: a point on its block's top face opens a sketch; other points are refused; tests
- [ ] 4.5 Docs: the sketching catalog page and the skill's note on sketching on a face

## 5. The monitor stand demo

- [ ] 5.1 `scripts/demo_monitor_stand.py`: pocket sketched on the top face with `face_point`; `create_reference_plane` drops out; camera to isometric after each cut and the fillet, behind a flag
- [ ] 5.2 Its live test: the volume matches 901 769 mm³ at the defaults, and the pocket follows a changed height after a rebuild
- [ ] 5.3 `docs/demos.md#monitor-stand`: the call list and count, and drop "one thing can't be matched"

## 6. Live bundle (one set, run together, then fixes one by one)

- [ ] 6.1 Live tests: feature order and `verify_model` on a part with `Plane1`; the dimension diagnostic (old walk vs new, counts) and the full listing on the stand; STL export path and file size; `create_sketch` on a face, the follow-the-height rebuild, a point in the air and a point on a fillet
- [ ] 6.2 Hand the user the bundle; fix each failure afterwards, one at a time
- [ ] 6.3 Re-record the monitor stand GIF with `SW_DEMO_RECORD`

## 7. Finish

- [ ] 7.1 CHANGELOG (Unreleased): Fixed (feature order, `verify_model`, dimension listing, STL), Added (`create_sketch` `face_point`)
- [ ] 7.2 Full mock suite at 100% coverage, ruff, `mkdocs build --strict`, progress files regenerated
- [ ] 7.3 Sign-off, PR (no attribution), archive, and the queue updated
