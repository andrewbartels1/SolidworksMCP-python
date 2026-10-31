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
- [x] 3.0f Fifth and sixth runs: still 4 overlaps. With a per-pass trace in
      the package result and `tests/scripts/layout_open_drawing.py` (reads
      and re-lays out the open drawing, writes the geometry to JSON), the
      causes were found by replaying the planner on the live geometry:
      every dimension below a view took its own row, so the 100 was pushed
      into the caption strip; the Ø text was measured three times too wide
      (`<MOD-DIAM>` counted as ten characters); the last step only checked.
      Fixes: dimensions share a row when they do not touch; each text code
      counts as one symbol; the last step lays the sheet out again, clear of
      each caption and note as measured. `tests/scripts/readme_demo_continue.py`
      finishes the demo from an open plate and drawing
- [x] 3.0g Seventh run: the plate drawing passed with no overlaps, the
      GD&T went on and the stack passed; the test hit pytest's 300 s limit
      in the assembly drawing (a paced demo is slower; now 1800 s). The
      position frame sat over the left dimensions: `add_gtol` on a dimension
      now lays the view out again with the frame as part of it. At the
      maintainer's request the assembly drawing keeps its isometric, with
      the BOM above it (`include_bom` on `generate_drawing_package`), and
      each exported PDF is shown as a frame (pypdfium2)
- [x] 3.0h Eighth run: everything up to the assembly drawing passed, and
      PS-02 came out right (BOM above the isometric), but its check found
      one overlap the error did not name. The package's error now names up
      to five overlaps. At the maintainer's request: a frame after every
      tool call, and the Top-plane mate starts at 60 mm and is stepped down
      to 20 so the top plate is seen coming into place; a window capture too
      narrow to read (SolidWorks minimised) gives a caption-only frame
- [x] 3.0i Ninth run: everything through the stack passed (the mate seen
      coming down in 8 frames); PS-02 failed on the Ø5.5 leader grazing the
      lower-left "10". The planner now keeps a leader 2 mm from any text
      (the check stays exact), and a conflict re-plans both dimensions in
      it, not only the first named. Orthographic views now show hidden
      lines (through holes dashed in the front and side views)
- [x] 3.0j Tenth run PASSED end to end (51 calls), but the GD&T frame was
      re-laid onto the PLAN caption: captions are inserted into the active
      view, not the sheet, so the sheet's notes missed them. Notes are now
      read from every view and measured from display data; `add_gtol`
      reports the frame box and obstacles it used. Recording (`-Record`):
      the mate comes down in 1 mm steps
- [x] 3.0k First recorded run: the GD&T frame no longer overlapped, but
      hung under PLAN on a long leader across two rows of dimensions; the
      slide took half the recording (40 captioned steps); the assembly's
      title block said "<not specified>". Now the hole note goes inside the
      plate near its hole when clear; the slide is 10 uncaptioned 4 mm steps;
      the package leaves an assembly's Material property and the demo sets
      it; the camera looks at the sketch from the top and at the part in
      isometric; captions are 30 px and wrap; 4x playback
- [x] 3.0l Final runs: captions FRONT/TOP/SIDE/ISOMETRIC VIEW; GD&T on
      the assembly drawing too; each build step captioned on both drawings;
      captions stamped as each step starts, so motion plays under its own
      call; 5x playback; the prompt held 4 s; the motion GIF shares one
      palette (41 MB to under 9 MB); local paths dropped from the transcript.
      Open: the assembly title block's MATERIAL still reads "<not
      specified>" (the format likely links SW-Material), and side views show
      no hidden lines although each reads back as set
- [x] 3.1 Run it with `live_demo.ps1 -CaptureDir docs/assets/demos/readme`.
      Untested live until now: a line-to-circle linear dimension, the
      sketch's fully-defined state, a drawing of an assembly without an
      isometric view, and a BOM at a given position
- [x] 3.2 Check the GIF reads well at README width, and is a sensible size

## 4. README

- [x] 4.1 Add the demo section near the top: the GIF, the prompt, one line on
      what it shows and that the calls are replayed, and the call list in a
      folded `<details>` block taken from the transcript
- [ ] 4.2 Build the docs (`mkdocs build --strict`) if any docs page links to
      the new section

## 5. Ship

- [ ] 5.1 Live sign-off with the maintainer, then the PR
- [ ] 5.2 Archive this change after merge
