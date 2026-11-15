## Context

See proposal.md for the six faults. Where each one comes from:

- **`list_features`' traversal:** the real adapter walks with
  `FirstFeature` and `GetNextFeature`, then always adds a
  `FeatureByPositionReverse(0..GetFeatureCount(True)-1)` pass. The forward
  walk can stop at the system folders. The second pass then finds the
  remaining features newest first, and they are appended in that order.
  The rows are de-duplicated but never sorted.
- **`verify_model`:** `_count_modelling_features` skips the first three
  `RefPlane` rows it meets, in row order. On the monitor stand the rows came
  newest first, so it skipped `Plane1`, `Right Plane` and `Top Plane` and
  counted `Front Plane` (seen in the session's `verify_model` reply).
- **`list_model_dimensions`:** it has its own forward-only walk, with no
  reverse pass, and reads `GetFirstDisplayDimension` on every feature,
  folders included. It found 0 with no name on the monitor stand, and all
  four when given each feature's name. The same walk serves both calls, so
  the cause is not proven. A block's full listing does work live
  (`test_dimensions_list_and_measure`).
- **`SaveAs2`:** the installed type library gives `IModelDocExtension.SaveAs2(Name,
  Version, Options, ExportData, ReferencePrefixOrSuffixText As String,
  AddTextAsPrefix As Boolean, Errors As Long by reference, Warnings As Long by
  reference)` (eight arguments; a first live run with seven, leaving out
  `Warnings`, failed with "Parameter not optional"). The adapter
  calls it with `(path, 0, 2, stl_data, None, "")`.
- **`create_sketch`:** it selects a plane by name (with locale aliases),
  then calls `InsertSketch`. Faces are already selected by coordinates
  elsewhere, for example `create_reference_plane`'s `face_point` and
  `select_face_edges`.

## Goals / Non-Goals

**Goals:**
- Feature and dimension listings that agree with the tree whatever the walk.
- A sketch on a face in one call, through the same adapter path as a plane.
- A demo whose recording shows each feature as it is made.

**Non-Goals:**
- Sketching on a curved face, or on a face of an assembly component.
- Changing `export_stl`'s inputs; only the call underneath changes.
- Finding why `GetNextFeature` stops at the folders. Both passes stay.

## Decisions

### 1. Sort `list_features` rows by tree position, in the adapter

Both passes number features by their place in the top-level tree. The
forward pass counts from 0, and the reverse pass uses
`count - reverse_pos - 1`, so a feature found by both gets the same number.
The adapter sorts each document's rows by `position` before returning
them, keeping each component's rows together as they are now. Every caller
then gets tree order: `verify_model`, the classifier, the bitmap, and
feature-tree diffs.

*Alternative:* sort only in `verify_model`. Rejected: every caller assumes
tree order, and only one has been caught by it.

### 2. `verify_model` skips default planes by position

Once rows are in tree order, the first three `RefPlane` rows are the
defaults. To guard against an adapter that doesn't sort, `verify_model`
also sorts its rows by `position` before counting. This keeps the rule
language-independent, as now: no plane names are matched.

### 3. `list_model_dimensions` walks with `list_features`

The adapter reads the features with the same two-pass traversal as
`list_features` (a shared walk, not a copy), then reads each one's display
dimensions. Folder rows are skipped, as nothing there has dimensions. Each
dimension is kept once, keyed by `full_name`, with `feature` set from the
part after `@`. With `feature_name`, the result keeps the dimensions whose
`feature` matches. A sketch's own dimensions (`D1@Sketch3`) keep the sketch
as their feature, so asking for the cut no longer returns the plane's offset.

*Live diagnostic:* a test builds the monitor stand at its defaults and
records, for the old and new walks, how many features each finds and how
many dimensions each lists. This proves the fix and explains the 0.

### 4. `SaveAs2` with its eight arguments

`ext.SaveAs2(path, 0, swSaveAsOptions_Silent, stl_data, "", False, errors, warnings)`
with `errors` and `warnings` by-reference Longs (`_byref_long`, as `RunMacro2` uses). When
`GetExportFileData` gives nothing, `ExportData` is a `VT_DISPATCH` null.
Success is the file existing. If `SaveAs2` writes nothing, `SaveAs3` runs
as now, and the tool's reply carries a `warning` that the STL options
weren't applied. The first `except` that retried `SaveAs2` without the data
goes: it was a second copy of the same wrong call.

### 5. `create_sketch(face_point=...)`

The input model takes exactly one of `plane` and `face_point`. Today `plane`
is required, so it becomes optional with the one-of check, and the error
names both. The adapter method gains `face_point: tuple[float, float, float]
| None`, through every adapter layer. The real adapter:

1. finds and selects the face with `_select_face_at_point`, the helper
   `create_reference_plane`'s `face_point` already uses live: it reads the
   body's faces, takes the one whose closest point is within 0.01 mm,
   refuses a face with no normal (curved), and selects it with
   `IFace2.Select4`. It works from the body's geometry, so it needs neither
   `SelectByID2` nor a rebuild first (decided at implementation, replacing
   the `SelectByID2` + `IsPlane()` route first planned here);
2. on no face, a curved face or a refused selection, clears the selection
   and raises `LookupError("face_point [x, y, z] mm is not on a flat face
   of the active part (<reason>)")`. One rule in `error_classifier.py`
   matches exactly that message and classifies it `invalid_input`; the
   shared "No face found at point" message stays `not_found` for
   `select_face_edges`;
3. calls `InsertSketch(True)`, and reads the new sketch's name as the
   plane path does.

The mock records the point and answers a point inside its block's top face
(mirroring its existing coordinate model), and refuses others.

*Alternative:* `face_name` (`Face<3>`). Rejected: agents don't know face
names, and every other face input in the tools is a point.

### 6. The demo

`scripts/demo_monitor_stand.py` sketches the pocket with
`create_sketch({"face_point": ...})` on the top face, at the stand's
centre, at its height. `create_reference_plane` drops out of the script.
For the recording, the script turns the camera to isometric and zooms to
fit after each cut and the fillet. It reuses the README demo's `_look`
pattern (`ShowNamedView2("", 7)`, `ViewZoomtofit2`), behind a flag the live
test sets, since it is demo-side COM and not a tool. The GIF is re-recorded
with `SW_DEMO_RECORD`, and the docs page's call list and count are updated.

## Risks / Trade-offs

- [Sorting changes `list_features`' order for callers that relied on the
  old order] → Only the broken case changes order: when the forward walk
  finishes, the rows are already in tree order. Feature-tree diffs key by
  name.
- [`SaveAs2` with the right arguments still fails on some versions] → The
  `SaveAs3` fallback stays, now with a `warning`, so no export is lost. The
  live test records which path wrote the file.
- [The diagnostic shows the 0 had another cause] → It runs in the bundle.
  If the new walk still misses dimensions, that is fixed after the bundle,
  one at a time, as agreed.
- [The pocket on the face changes the stand's volume] → No: the face is at
  the same height the offset plane was. The live test checks the volume
  against the recorded 901 769 mm³.
