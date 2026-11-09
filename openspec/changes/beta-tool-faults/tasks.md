## 1. Shared pieces

- [ ] 1.1 `input_compat.py`: `REMOVED_INPUTS` and `reject_removed_inputs`, called from `normalize_input`; tests for a removed field (refused with its pointer), a kept alias (accepted), and an unknown extra (still accepted)
- [ ] 1.2 `features.py`: lift `_resolve_profile_sketch` out of the cut-extrude code; the cut uses it unchanged (existing cut tests pass untouched)

## 2. Sketch and feature inputs (live batch 1)

- [ ] 2.1 `create_extrusion`: pass `sketch_name` through `ExtrusionParameters` to the resolver; remove `direction`; mock matches; tests for a named sketch, a missing sketch, and no name
- [ ] 2.2 `create_revolve`: `sketch_name` through the resolver, `axis_entity` optional and selected with mark 4 when it names a reference axis; remove `direction` and its echo; tests
- [ ] 2.3 `create_sketch`: rename the new sketch to `sketch_name`; on refusal keep the original name and return a `warning`; the reply always gives the tree's name; tests
- [ ] 2.4 `create_part`: apply `material` after the part opens; an unknown material gives a `warning`, not an error; tests
- [ ] 2.5 Live batch 1 in `tests/live/test_live_sw_beta_tools.py` (extrude an earlier sketch, a missing sketch, revolve about `Axis1`, a named sketch used by a cut, a part with AISI 304); run with the user's permission; settle design decision 5's route

## 3. Patterns, mirror and delete (live batch 2)

- [ ] 3.1 `pattern_circular` and `mirror_feature`: any volume change beyond the tolerance succeeds; add `volume_change`; mock and tests for growth, a cut, and no change
- [ ] 3.2 `delete_feature`: the adapter returns `removed_features` by name from before/after lists; the tool's message names the dependents; mock and tests
- [ ] 3.3 Live batch 2 (a ring of 6 holes, a mirrored cut, deleting a sketch with its cut)

## 4. Measurements (live batch 3)

- [ ] 4.1 `calculate_mass_properties`: inertia ×1e6 to kg·mm²; remove its 4 inputs; tests including the 100 × 50 × 20 mm block's hand values
- [ ] 4.2 `check_interference`: `include_hidden` → `ignore_hidden`; remove `tolerance` and `check_all_components`; tests
- [ ] 4.3 `get_material`: density in kg/m³ or `null`; mock and tests
- [ ] 4.4 Live batch 3 (block inertia, a hidden overlapping component both ways, AISI 304 density)

## 5. Files and macros (live batch 4)

- [ ] 5.1 `save_as`: refuse an existing path unless `overwrite`; tests that the file is untouched
- [ ] 5.2 `save_file`: remove `force_save`; the five `export_*` tools: remove `options`; delete `ExportSTEPInput`, `ExportIGESInput` and `ExportSTLInput`; tests
- [ ] 5.3 `execute_macro`: loop `repeat_count` (1-100) with `pause_between_runs`, stop at the first failure, `runs_completed` in the reply; decide each other unused field by design decision 1 and record it here; tests
- [ ] 5.4 Live batch 4 (`save_as` over an existing file both ways, `save_file`, each export, a macro run 3 times)

## 6. Drawings and the tutorial (live batch 5)

- [ ] 6.1 `create_assembly`: remove `components`; `create_drawing`: remove `model_path` and `sheet_format`; tests
- [ ] 6.2 `create_technical_drawing`: remove `template`, `sheet_size`, `title` and `output_path`; tests
- [ ] 6.3 `add_drawing_view`: refuse an `operation` other than `add`; tests
- [ ] 6.4 `sketch_tutorial_simple_hole`: its hole step uses `create_cut_extrude`; test that no step passes a negative depth
- [ ] 6.5 Live batch 5 (an assembly, a drawing, three standard views, `add_drawing_view` refusing `remove`, the tutorial's steps run as written)

## 7. Promote and document

- [ ] 7.1 Each tool's description loses its fault sentence and states what the honoured inputs do
- [ ] 7.2 `support_levels.py`: the 23 tools move to `stable`; regenerate with `python -m solidworks_mcp.progress.generate`
- [ ] 7.3 `errors-and-limits.md`: remove the 11 fixed rows (the `add_mate` edge row stays); the queue's "Small faults" list loses them
- [ ] 7.4 CHANGELOG: **Fixed** (the wrong results), **Changed** (every removed input, with its replacement; inertia now in kg·mm²)
- [ ] 7.5 Full mock suite at 100% coverage, ruff, `mkdocs build --strict`
- [ ] 7.6 Live-demo sign-off with the user before the PR
