## 1. Demo test

- [x] 1.1 Write `tests/live/test_live_sw_readme_demo.py`: the prompt and plan
      frame; the plate; `verify_model` on the plate; two plates mated 10 mm
      apart; `verify_model` on the stack with the gap read from its height;
      the drawing; the call transcript
- [x] 1.2 Lint it, pass the test-layout check, and dry-run every call against
      the mock adapter to confirm the tool names and argument shapes

## 2. First live run (2026-10-30) and what it found

- [x] 2.1 First run: the modelling and both checks passed. The drawing had
      only two dimensions (the sketches had none), showed "Material <not
      specified>" (it was a drawing of the assembly), and the BOM failed:
      placed by the A3 format's anchor it ran off the top of the sheet
- [x] 2.2 The plate becomes one sketch with every size and hole position
      dimensioned (each hole located from two edges with a line-to-circle
      linear dimension), extruded once
- [x] 2.3 Two drawings: the plate's (AISI 1020, all dimensions, centre marks
      on the plan view) and the assembly's (no isometric view, the BOM placed
      in that free cell)
- [x] 2.4 `insert_bom_table`: slide a table placed by the anchor onto the
      sheet and report `moved_onto_sheet`; a given position is never moved
- [x] 2.5 Mock adapter: `insert_bom_table` reports `moved_onto_sheet`
- [x] 2.6 Tests for 2.4 and 2.5: slid off the top, slid off the left and
      bottom, a given position off the sheet is still an error, a table that
      cannot be slid on is an error; 100 % coverage of the new code
- [x] 2.7 `auto_center_marks` normalises its input (a dict raised); test
- [x] 2.8 `add_line` reads the mock wrapper's `id` key; test

## 3. Live runs (only after the maintainer says go)

- [x] 3.0 Second run (2026-10-30): the first hole's line-to-circle
      dimension failed; `Extension.AddDimension` with the line's own
      placement returned nothing. `add_sketch_dimension` now places a
      two-entity linear dimension midway between them and tries
      `AddDimension2`, then the circle's centre point, then
      `Extension.AddDimension`; unit-tested, `sketch.py` at 100 %
- [x] 3.0a The README links every runnable demo script (Demos section);
      the Pack-and-Go demo is left out because it needs a local file
- [x] 3.0b Third run: every hole dimension, the plate check and the drawing
      build worked; the drawing failed its overlap check because the hole
      dimensions were imported into the front view, where the holes stack.
      Fixes: each model dimension now stays in the view that took the most
      dimensions (the plan); one Ø5.5 plus equal relations instead of four;
      sketch dimension text placed outside the outline; a general-tolerance
      note (ISO 2768-m). Feature control frames wait for #182
- [x] 3.0c `add_sketch_constraint` normalises its input (a dict raised); test
- [x] 3.0d Fourth run: everything landed in the plan view; 4 overlaps were
      left, all from the layout's model of the drawing being wrong, not from
      COM. The Ø leader was modelled as moving with its text (it stays on
      the hole), and the layout never re-planned from what SolidWorks really
      drew. Fixed in `dimension_layout.py` (leader anchored on its feature,
      outward candidates, `fixed` dimensions) and `_arrange_layout` (up to
      three passes from read-back geometry); 100 % coverage
- [x] 3.0e GD&T, at the maintainer's request: `add_gtol` (feature control
      frame, on a drawing dimension, an edge or free) and `add_datum_tag`,
      in the adapter, all four layers, the mock and the tools, with tests;
      the demo puts datums A, B, C on the plate and ⊕ Ø0.2 Ⓜ A|B|C on the
      Ø5.5. First live use of `InsertGtol` and `InsertDatumTag2`
- [ ] 3.1 Run it with `live_demo.ps1 -CaptureDir docs/assets/demos/readme`.
      Untested live until now: a line-to-circle linear dimension, the
      sketch's fully-defined state, a drawing of an assembly without an
      isometric view, and a BOM at a given position
- [ ] 3.2 Check the GIF reads well at README width, and is a sensible size

## 4. README

- [ ] 4.1 Add the demo section near the top: the GIF, the prompt, one line on
      what it shows and that the calls are replayed, and the call list in a
      folded `<details>` block taken from the transcript
- [ ] 4.2 Build the docs (`mkdocs build --strict`) if any docs page links to
      the new section

## 5. Ship

- [ ] 5.1 Live sign-off with the maintainer, then the PR
- [ ] 5.2 Archive this change after merge
