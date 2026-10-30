## 1. Demo test

- [x] 1.1 Write `tests/live/test_live_sw_readme_demo.py`: the prompt and plan
      frame; the drilled plate with `measured_change`; `verify_model` on the
      plate; two plates mated 10 mm apart; `verify_model` on the stack with
      the gap read from its height; `generate_drawing_package` with extra
      notes; `insert_bom_table`; the call transcript
- [x] 1.2 Lint it, pass the test-layout check, and dry-run every call against
      the mock adapter to confirm the tool names and argument shapes

## 2. Live run (only after the maintainer says go)

- [ ] 2.1 Run it with `live_demo.ps1 -CaptureDir docs/assets/demos/readme`;
      fix anything it finds (the Right Plane mate, a drawing of an assembly
      and a BOM listing one part twice have not run live before)
- [ ] 2.2 Check the GIF reads well at README width, and is a sensible size

## 3. README

- [ ] 3.1 Add the demo section near the top: the GIF, the prompt, one line on
      what it shows and that the calls are replayed, and the call list in a
      folded `<details>` block taken from the transcript
- [ ] 3.2 Build the docs (`mkdocs build --strict`) if any docs page links to
      the new section

## 4. Ship

- [ ] 4.1 Live sign-off with the maintainer, then the PR
- [ ] 4.2 Archive this change after merge
