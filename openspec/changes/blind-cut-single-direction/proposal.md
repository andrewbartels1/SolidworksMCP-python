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

- A blind cut tries a single-ended `FeatureCut4`/`FeatureCut3` (`Sd=True`)
  first. If that builds nothing, it retries the double-ended form
  (`Sd=False`, zero-depth blind Direction 2), after reselecting the sketch.
  The first live run of the fix showed that each form works for only one
  case. Single-ended works from a sketch inside the body; from a face sketch
  its Direction 1 points out of the part. Double-ended works from a face
  sketch, as it has since June, but is rejected from an internal one.
- The result's `parameters.single_direction` reports which form built the
  feature.
- Through All keeps #192's forms. The SW-version check now picks only
  `OptimizeGeometry`; it no longer decides `Sd`.
- The live test `test_blind_cut_still_cuts_one_way` loses its `xfail`, and a
  test for Through All in one direction is added.
- `docs/agents/com-api-pitfalls.md` gets entry #35 with the table of which
  form works where.

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
