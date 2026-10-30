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
  - a 100 x 50 x 10 mm AISI 1020 plate with four M5 clearance holes;
    `measured_change` shows the volume each feature added or removed;
  - `verify_model` on the plate: volume, mass, size, feature and body counts;
  - an assembly with the plate inserted twice, held 10 mm apart by three
    mates; `verify_model` checks the counts and that nothing overlaps, and
    the gap is read from the assembly's height;
  - `generate_drawing_package` on the assembly, with each build step shown,
    plus extra notes and the title block; then `insert_bom_table`.
- The test's frames become one GIF, plus the call transcript
  (`plate_stack_calls.json`), under `docs/assets/demos/readme/`.
- README: a short demo section near the top with the GIF, the prompt, and
  the calls folded underneath. It says plainly that the calls are replayed,
  not a recorded model session.

Out of scope: recording a real model session, generating the reproduction
script, and the bracket itself (all #147); the rest of the README rewrite.

No COM or adapter code changes. The demo only calls existing tools.

## Capabilities

### New Capabilities

- `docs/readme-demo`: the README shows a live, checked demo from prompt to
  drawing, and the test that makes it can be rerun.

### Modified Capabilities

None.

## Impact

- New: `tests/live/test_live_sw_readme_demo.py`,
  `docs/assets/demos/readme/` (GIF, frames and transcript).
- Changed: `README.md`.
- The test reuses helpers from `tests/live/test_live_sw_drawing_package_tools.py`.
