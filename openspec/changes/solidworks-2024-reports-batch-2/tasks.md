## 1. Reproduce on 2026

- [x] 1.1 `tests/live/test_live_sw_2024_reports_batch2.py`: one test per report, run on SolidWorks 2026
- [x] 1.2 Probes for #262 (BOM), #269 (origin), #271 (hole wall), #274 (thread size)

## 2. Fixes

- [x] 2.1 #267 wrappers forward `pack_and_go_assembly`; a test that both forward every adapter method
- [x] 2.2 #266 `set_dimension`, #268 `GetConstrainedStatus`, #270 extrusion after a rename, #271 face tolerance, #272 pattern angles
- [x] 2.3 #273 section view moved, #274 coarse thread size read back, #275 note top-left, #262 BOM re-placed
- [x] 2.4 #269 `origin` and `.start`/`.end` in `add_sketch_constraint`; #276 `save_as` wording and `as_copy` (`save_copy`)

## 3. Release compatibility

- [x] 3.1 `compat.invoke` / `read` / `fallbacks` / `release_year`; the equation tools through it (#265)
- [x] 3.2 The selftest summary names the fallbacks
- [x] 3.3 COM pitfalls 40-44; CHANGELOG

## 4. Checks and sign-off

- [x] 4.1 Unit suite at 100% coverage, ruff, mypy, mkdocs strict
- [x] 4.2 Every test in the live file passes on SolidWorks 2026
- [ ] 4.3 The user reviews; the reporter reruns the selftest and the reports on 2024 (the user posts replies)
- [x] 4.4 Asked: the hole offset is to be fixed now; Save As and Save a Copy kept apart

## 5. Follow-ups from the full live run (2026-11-25)

- [x] 5.1 `create_hole` moves the hole's position sketch point exactly onto `face_point` (`_place_holes`); live: axis at (-20.000, -12.000), was (-20.043, -12.039)
- [x] 5.2 `create_revolve` takes a sketch line's id as `axis_entity` (`EXTSKETCHSEGMENT` by name, mark 4); live: the verify_model revolve adds 12566.37 mm3
- [x] 5.3 `SaveAs3` / `SaveAs2` options named (`SAVE_AS_COPY`, `SAVE_AS_SILENT`); export descriptions say they write a copy
- [x] 5.4 The U-joint replay leaves the live suite (`demo_ujoint_replay.py`); its calls and today's answers are recorded, the nine differences explained
- [x] 5.5 The measure live test reads a face's centre, not an edge point
- [x] 5.6 Rerun the live files that make holes and revolves: 7 files pass; `drawing_pack` failed once in `arrange_dimensions` (one auto-dimension outside the frame) and passed on rerun, a follow-up
