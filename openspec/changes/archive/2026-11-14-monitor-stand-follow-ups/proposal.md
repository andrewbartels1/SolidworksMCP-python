## Why

Building the monitor stand demo (issue #206, queue item 9) turned up five tool
faults and one missing ability. On a real part, `verify_model` counted
`Front Plane` and skipped `Plane1`, and `list_model_dimensions` with no
feature name found nothing. The same dimension was listed under two
features. Every STL export logged a type mismatch and fell back to a path
that can't merge bodies. No tool could start a sketch on a face of the body.
Each one misleads an agent reading a finished part, and the demo recording
misses the cuts and fillet because the camera never turns.

## What Changes

- **`list_features` returns rows in tree order.** The real adapter walks
  forward with `GetNextFeature`, then always adds a `FeatureByPositionReverse`
  pass, because the forward walk can stop at the system folders. When it
  stops, the remaining rows arrive newest first. The rows are now sorted by
  `position`, and both passes give the same position to the same feature.
- **`verify_model` skips the three default planes by tree order**, so a
  reference plane the agent made (`Plane1`) is counted and `Front Plane` is
  not, whatever order the rows arrive in.
- **`list_model_dimensions` finds every dimension with no feature name.**
  It walks the tree the way `list_features` does (both passes), and lists
  each dimension once, under the feature its full name's `@` suffix names
  (`D1@Plane1` under `Plane1`, never also under the cut on that plane). Why
  the old walk found none is not proven, so a live diagnostic records
  where it went wrong.
- **STL export calls `IModelDocExtension.SaveAs2` with its eight arguments**
  (`Name, Version, Options, ExportData, ReferencePrefixOrSuffixText,
  AddTextAsPrefix, Errors, Warnings`). The adapter passed six, with the wrong types,
  so the call always failed with a type mismatch and `SaveAs3` wrote a file
  without the merged-bodies option. The warning goes, and `SaveAs3` stays
  only as the fallback for a `SaveAs2` that writes nothing.
- **`create_sketch` takes `face_point`** (`[x, y, z]` in mm on a flat face
  of the body) in place of `plane`, and opens the sketch on that face. It
  must name exactly one of `plane` and `face_point`. A point that is not on
  a flat face fails with `invalid_input`.
- **The monitor stand demo** cuts its pocket on a sketch on the stand's top
  face (via `face_point`), so the pocket follows a hand-edited height as the
  user's finished part does. Its camera turns to isometric after each cut
  and the fillet, and the GIF is re-recorded.

No breaking changes: `plane` stays as it is; `face_point` is optional.

## Capabilities

### New Capabilities

- `tools/dimension-listing`: `list_model_dimensions` lists every dimension
  in the model once, under the feature that owns it.
- `tools/stl-export`: `export_stl` writes the file through `SaveAs2` with its
  export options, without a type-mismatch warning.
- `tools/sketch-on-face`: `create_sketch` opens a sketch on a flat face of
  the body given a point on it.

### Modified Capabilities

- `tools/list-features`: the rows come in tree order, whichever traversal
  found them.
- `tools/model-verification`: the feature count skips the three default
  planes by tree order, so a plane the agent made is counted.

## Impact

- **COM and adapter code:** this change touches `pywin32_adapter.py`
  (`list_features`' traversal, `_save_stl_with_extension`),
  `adapters/solidworks/documentation.py` (`list_model_dimensions`) and
  `adapters/solidworks/sketch.py` (`create_sketch` on a face). `create_sketch`'s
  new argument runs through `base.py`, `circuit_breaker.py`,
  `connection_pool.py` and `mock_adapter.py`. All COM work stays on the
  connect thread inside `_handle_com_operation`. The `SaveAs2` call needs a
  by-reference `Errors` VARIANT, and face selection needs the `VT_DISPATCH`
  null callout (runbook #11) and `ForceRebuild3` first (runbook #13).
- **Tools:** `sketching.py` (`CreateSketchInput`), `analysis.py`
  (`_count_modelling_features`), `engineering_data.py` (description only).
- **Demo:** `scripts/demo_monitor_stand.py`, its live test and
  `docs/demos.md#monitor-stand`, with the GIF re-recorded.
- **Docs:** the sketching tool catalog page, the skill's workflow notes on
  sketching on a face, and the CHANGELOG.
- **Live tests:** one bundled set run at the end; failures are fixed one by
  one afterwards.
