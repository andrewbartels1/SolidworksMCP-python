## 1. Shared pieces

- [x] 1.1 `input_compat.py`: `REMOVED_INPUTS` and `reject_removed_inputs`, called from `normalize_input`; tests for a removed field (refused with its pointer), a kept alias (accepted), and an unknown extra (still accepted)
- [x] 1.2 `features.py`: lift `_resolve_profile_sketch` out of the cut-extrude code; the cut uses it unchanged (existing cut tests pass untouched)

## 2. Sketch and feature inputs (live batch 1)

- [x] 2.1 `create_extrusion`: pass `sketch_name` through `ExtrusionParameters` to the resolver; remove `direction`; mock matches; tests for a named sketch, a missing sketch, and no name
- [x] 2.2 `create_revolve`: `sketch_name` through the resolver, `axis_entity` optional and selected with mark 4 when it names a reference axis; remove `direction` and its echo; tests
- [x] 2.3 `create_sketch`: rename the new sketch to `sketch_name`; on refusal keep the original name and return a `warning`; the reply always gives the tree's name; tests. Live batch 1 showed an open sketch can't be renamed, so `exit_sketch` gives the name (design decision 5, settled)
- [x] 2.4 `create_part`: apply `material` after the part opens; an unknown material gives a `warning`, not an error; tests
- [x] 2.5 Live batch 1 in `tests/live/test_live_sw_beta_tools.py` (extrude an earlier sketch, a missing sketch, revolve about `Axis1`, a named sketch used by a cut, a part with AISI 304); run with the user's permission; settle design decision 5's route

## 3. Patterns, mirror and delete (live batch 2)

- [x] 3.1 `pattern_circular` and `mirror_feature`: any volume change beyond the tolerance succeeds; add `volume_change`; mock and tests for growth, a cut, and no change
- [x] 3.2 `delete_feature`: the adapter returns `removed_features` by name from before/after lists; the tool's message names the dependents; mock and tests
- [x] 3.3 Live batch 2 (a ring of 6 holes, a mirrored cut, deleting a sketch with its cut)

## 4. Measurements (live batch 3)

- [x] 4.1 `calculate_mass_properties`: inertia ×1e6 to kg·mm²; remove its 4 inputs; tests including the 100 × 50 × 20 mm block's hand values
- [x] 4.2 `check_interference`: `include_hidden` → `ignore_hidden`; remove `tolerance` and `check_all_components`; tests
- [x] 4.3 `get_material`: density in kg/m³ or `null`; mock and tests
- [x] 4.4 Live batch 3 (block inertia, a hidden overlapping component both ways, AISI 304 density)

## 5. Files and macros (live batch 4)

- [x] 5.1 `save_as`: refuse an existing path unless `overwrite`; tests that the file is untouched
- [x] 5.2 `save_file`: remove `force_save`; the five `export_*` tools: remove `options`; delete `ExportSTEPInput`, `ExportIGESInput` and `ExportSTLInput`; tests
- [x] 5.3 `execute_macro`: loop `repeat_count` (1-100) with `pause_between_runs`, stop at the first failure, `runs_completed` in the reply; decide each other unused field by design decision 1 and record it here; tests. Decided: `proc_name` (read by the adapter but undocumented) is now a field; `parameters`, `execution_parameters`, `target_file`, `execution_mode`, `pause_on_error` and `log_execution` are removed (nothing read them)
- [x] 5.4 Live batch 4 (`save_as` over an existing file both ways, `save_file`, each export, a macro run 3 times)

## 6. Drawings and the tutorial (live batch 5)

- [x] 6.1 `create_assembly`: remove `components`; `create_drawing`: remove `model_path` and `sheet_format`; tests
- [x] 6.2 `create_technical_drawing`: remove `template`, `sheet_size`, `title` and `output_path`; tests
- [x] 6.3 `add_drawing_view`: refuse an `operation` other than `add`; tests
- [x] 6.4 `sketch_tutorial_simple_hole`: its hole step uses `create_cut_extrude`; test that no step passes a negative depth
- [x] 6.5 Live batch 5 (an assembly, a drawing, three standard views, `add_drawing_view` refusing `remove`, the tutorial's steps run as written)

## 7. Promote and document

- [x] 7.1 Each tool's description loses its fault sentence and states what the honoured inputs do
- [x] 7.2 `support_levels.py`: the 23 tools move to `stable`; regenerate with `python -m solidworks_mcp.progress.generate`
- [x] 7.3 `errors-and-limits.md`: remove the 11 fixed rows (the `add_mate` edge row stays); the queue's "Small faults" list loses them
- [x] 7.4 CHANGELOG: **Fixed** (the wrong results), **Changed** (every removed input, with its replacement; inertia now in kg·mm²)
- [x] 7.5 Full mock suite at 100% coverage, ruff, `mkdocs build --strict`
- [ ] 7.6 Live-demo sign-off with the user before the PR

## Notes from the implementation

- `create_technical_drawing` had three more unread fields than design
  decision 1 listed (`sheet_format`, `scale`, `auto_populate_views`); all are
  removed by the same rule. `projection`, which the adapter already read but
  the schema didn't show, is now a field.
- `calculate_mass_properties` had a branch for an adapter method no adapter
  implements; it returned raw numbers and skipped the unit conversion, so it
  is deleted.
- Without `sketch_name`, `create_extrusion` still uses the sketch `exit_sketch`
  just closed without reselecting it, as before, so a thin wall from an open
  chain keeps working; only a named sketch goes through the strict resolver.
- `get_material` reads the density from the material's `.sldmat` library
  entry (the `DENS` value, kg/m³), the same files `list_available_materials`
  reads.
- Live batch 2: `EditDelete` would not delete a sketch a cut used ("did
  not remove"). `delete_feature` now calls `DeleteSelection2` with
  `swDelete_Children` (1; `swDelete_Absorbed` is 2, both read from
  swconst.tlb). That still returned False with the sketch selected:
  SolidWorks won't delete a sketch a feature uses. So when the plain delete
  returns False, the features built from it (`IFeature::GetChildren`) are
  deleted with `swDelete_Children | swDelete_Absorbed`, which takes the
  sketch with them. Deleting a cut still leaves its absorbed sketch.
- Inertia products (batch 3): the path SolidWorks 2026 takes,
  `IMassProperty.GetMomentOfInertia(0)`, returns the row-major 3 x 3 tensor,
  and the adapter's indices 1, 2 and 5 are Ixy, Ixz and Iyz, as they should
  be. The fallback for older versions, `IModelDoc2.GetMassProperties`, ends
  Lxy, Lzx, Lyz (API docs) and was mapping index 10 to Iyz and 11 to Ixz;
  fixed, with a test of the order. The live block test passes (its products
  are zero, so it checks the moments only).
