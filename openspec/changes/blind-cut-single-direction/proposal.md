## Why

On SolidWorks 2025 and 2026, a blind `create_cut_extrude` from a sketch inside
the body returns no feature (issue #193). The adapter tells `FeatureCut4` that
the cut is double-ended (`Sd=False`) with a zero-depth blind Direction 2.
SolidWorks rejects that from an internal sketch. From a sketch on a face it
happens to work, because Direction 2 points into empty space. That is why the
bug went unnoticed.

The cause is a misread argument. Commit 69d3dbd (2026-06-13) passed
`is_through` into the `Sd` slot, but `Sd` means "single direction", not "is
through". Through All cuts were right by coincidence. Blind cuts on SW 2025+
became double-ended. Older versions always passed `Sd=True` and were never
affected. Contributor PR #192 kept the value and labelled it intentional.

## What Changes

- Every one-direction cut passes `Sd=True` to `FeatureCut4` and `FeatureCut3`,
  on every SolidWorks version. That covers Blind and Through All.
- `Sd=False` is used only for a cut that really goes both ways. Today that is
  Through All both ways, the double-ended form #192 introduces.
- The SW-version check stays only for `OptimizeGeometry`. It no longer
  decides `Sd`.
- The live test `test_blind_cut_still_cuts_one_way` loses its `xfail` and
  becomes a normal regression test.
- `docs/agents/com-api-pitfalls.md` gets an entry explaining `Sd`.

This builds on #192's refactor of `create_cut_extrude` (one argument builder,
plus a list of `(label, Sd, T1, T2)` forms to try). It lands after #192 merges.

## Capabilities

### New Capabilities
- `tools/cut-extrude`: which end conditions `create_cut_extrude` accepts, which
  way each one cuts, and that a blind cut works wherever its sketch sits
  (inside the body or on a face).

### Modified Capabilities
None.

## Impact

- **COM and adapter code.** Changes `src/solidworks_mcp/adapters/solidworks/features.py`
  (`create_cut_extrude`), which is reached through `pywin32_adapter`. COM
  threading and late binding are unaffected: no new calls, no new dispatches.
  Only one argument value changes.
- The mock adapter needs no change, because it never looks at `Sd`.
- Unit tests: `tests/solidworks_mcp/adapters/solidworks/test_features.py`. The
  version and end-condition table expects `Sd=True` for blind cuts on 33.x
  and 34.x.
- Live tests: `tests/live/test_live_sw_contributor_fixes.py` (remove the
  xfail) and `tests/live/test_live_sw_verify_model.py` (the face-sketch hole
  must still remove 142.5 mm³).
- Depends on PR #192. Closes #193.
