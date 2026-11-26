## Why

The SolidWorks 2024 SP5 reporter of #255-#257 filed twelve more reports
(#265-#276) and a selftest summary (#264). We have no 2024 install. Each
report was first reproduced on SolidWorks 2026: ten fail here too, so they
are ours; two (#265 equations, #275 note position) are 2024 only. The user
asked (2026-11-24) for those fixed without changing what works on 2026, and
for a robust way to handle the differences between releases.

## What Changes

- **A release-compatibility layer** (`adapters/solidworks/compat.py`). The
  difference #265 shows (a member answering as the other dispatch kind) is
  handled in one place: `invoke` / `read` make each call as before and only
  on "Member not found" retry with either dispatch kind. Members that needed
  it are named in the selftest summary. A difference in *where* something
  lands (#275) is handled by measuring and correcting, which is a no-op on
  2026.
- **The reports that reproduce on 2026**, fixed and checked live: #266
  `set_dimension` "this" in one of several configurations, #267
  `pack_and_go_assembly` not forwarded by the wrappers, #268
  `check_sketch_fully_defined`, #270 an extrusion after a named sketch,
  #271 a Hole Wizard wall in `add_mate`, #272 a negative pattern direction,
  #273 a section view's position, #274 a coarse cosmetic thread's size.
- **Two requests**: #269 relations to the sketch origin and to end points;
  #276 `save_as` worded as Save As, with `as_copy`.
- **#262's BOM placement really moves the table** (the slide it had never
  moved an anchored table).

Not in this change: `create_hole` places a hole about 0.04 mm off its point
(found while probing #271; needs the user's OK to change hole placement);
the export path passes `SaveAs3` option 2 commented as "Silent", which is
`swSaveAsOptions_Copy` (exports work; left as it is).

## Capabilities

### New Capabilities

- `adapters/release-compat`: calls that differ between releases.

### Modified Capabilities

None (the fixes keep each tool's inputs; `save_as` gains `as_copy`,
`add_sketch_constraint` accepts more entity ids).

## Impact

- New `compat.py`; changes in `io.py`, `sketch.py`, `features.py`,
  `part_features.py`, `drawing_pack.py`, `drawing_standard.py`,
  `face_selection.py`, `equations.py`, the wrappers and the selftest report.
- New adapter method `save_copy`.
- Live: `tests/live/test_live_sw_2024_reports_batch2.py`, one test per
  report, all passing on SolidWorks 2026.
