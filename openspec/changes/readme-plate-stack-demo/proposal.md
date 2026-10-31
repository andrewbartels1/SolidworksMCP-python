## Why

The README is all text. A new visitor can't see what the server does until
they install it. The full bracket demo (#147) needs session recording and
script generation that don't exist yet, so the README stays bare until those
land. This change puts a demo at the top now, built only from tools that
have already passed live on SolidWorks 2026. It is the first phase of the
README rewrite on the roadmap.

## What Changes

- New live test `tests/live/test_live_sw_readme_demo.py`. It starts from a
  prompt and the plan worked out from it, then makes the tool calls that
  answer it, through the registered MCP tools:
  - a 100 x 50 x 10 mm AISI 1020 plate with four M5 clearance holes, from
    one sketch with every size and hole position dimensioned, so the drawing
    can carry every dimension needed to make it; `measured_change` shows the
    volume the extrude added;
  - `verify_model` on the plate: volume, mass, size, feature and body counts;
  - the plate's drawing (`generate_drawing_package`, each build step shown):
    the model dimensions, centre marks on the holes (`auto_center_marks`),
    notes, and AISI 1020 in the title block;
  - an assembly with the plate inserted twice, held 10 mm apart by three
    mates; `verify_model` checks the counts and that nothing overlaps, and
    the gap is read from the assembly's height;
  - the assembly's drawing with a BOM (`insert_bom_table`) listing the plate
    twice.
- Fixes the first live run found:
  - `insert_bom_table` placed by the sheet format's anchor ran off the top
    of the ISO A3 sheet and failed. A table placed by the anchor is now slid
    onto the sheet (`moved_onto_sheet` in the reply); a table at a given
    `x_mm`/`y_mm` is still never moved. Adapter change, with the mock
    adapter's reply updated to match.
  - `auto_center_marks` did not normalise its input, so a plain dict raised
    an internal error instead of running.
  - `add_line` reported `id: None` through the mock adapter, whose legacy
    line wrapper returns `id` rather than `entity_id`.
- The test's frames become one GIF, plus the call transcript
  (`plate_stack_calls.json`), under `docs/assets/demos/readme/`.
- README: a short demo section near the top with the GIF, the prompt, and
  the calls folded underneath. It says plainly that the calls are replayed,
  not a recorded model session.

Out of scope: recording a real model session, generating the reproduction
script, and the bracket itself (all #147); the rest of the README rewrite.

One adapter change: `insert_bom_table` may move the table it inserted, with
`IAnnotation::SetPosition`, the call this module already uses to place
notes. Everything else is tool-level or test-only.

## Capabilities

### New Capabilities

- `docs/readme-demo`: the README shows a live, checked demo from prompt to
  drawing, and the test that makes it can be rerun.

### Modified Capabilities

None.

## Impact

- New: `tests/live/test_live_sw_readme_demo.py`,
  `docs/assets/demos/readme/` (GIF, frames and transcript).
- Changed: `README.md`; `adapters/solidworks/drawing_standard.py` and
  `adapters/mock_adapter.py` (BOM placement); `tools/drawing.py`
  (`auto_center_marks` input); `tools/sketching.py` (`add_line` id).
- The test reuses helpers from `tests/live/test_live_sw_drawing_package_tools.py`.
