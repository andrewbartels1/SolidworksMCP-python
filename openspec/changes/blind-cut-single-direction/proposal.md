## Why

On SolidWorks 2025 and 2026, a blind `create_cut_extrude` from a sketch inside
the body returns no feature (issue #193).

Live probes on SW 2026 (2026-11-01) found two separate problems:

- **A misread argument.** Commit 69d3dbd (2026-06-13) passed `is_through`
  as `FeatureCut4`'s first argument, `Sd`. But `Sd` means "single
  direction", so every blind cut on SW 2025+ was sent as a double-ended cut
  with a zero-depth second side. SolidWorks builds nothing from that form,
  from any sketch.
- **The direction is the sketch normal.** A one-way cut goes along the
  sketch plane's normal. From a sketch on a face, or on a plane at the edge
  of the body (a Top Plane sketch under a block extruded up from it), that
  normal points away from the material. A correct single-ended cut then
  finds nothing to remove.

Face-sketch cuts only seemed to work. The `FeatureCut3` fallback on main
passed `D2 = depth`, so it built a double-ended cut whose second side
happened to go into the block. #192 fixed that fallback's arguments, which
exposed both problems.

Agents also had no way to know any of this. The tool description didn't
say which way a cut goes, and the error said only "returned no feature".

## What Changes

- **One direction (Blind and Through All):** the cut is single-ended
  (`Sd=True`) in the requested direction. If that builds nothing, it is
  retried once in the opposite direction, after the sketch is reselected.
  This is what the SolidWorks UI does: it cuts into the material. Through
  All both ways keeps the forms from #192.
- **Reporting the flip:** the adapter result's `parameters.direction_flipped`
  and the tool reply's `cut_extrude.direction_flipped` say when the flip
  happened. The tool's success message says it too.
- **The error when nothing is built:** it names the forms that were tried,
  and the depth, and says what to change. The classifier gives it a new
  `error_type`, `feature_not_built`, whose hint says to change the inputs
  rather than retry the same call.
- **Documentation:**
  - the `create_cut_extrude` description and its `reverse_direction` and
    `end_condition` field descriptions explain the direction rule;
  - the tool catalog's modeling page has a "Which way a cut goes" note;
  - its error table lists `feature_not_built`;
  - COM pitfall #35 records the probe table.
- **SW version:** the version check now picks only `OptimizeGeometry`; it
  no longer decides `Sd`.
- **Live tests:** `test_blind_cut_still_cuts_one_way` loses its `xfail`,
  and a Through All one-way test is added.

## Capabilities

### New Capabilities
- `tools/cut-extrude`: which way each end condition cuts; that a one-way cut
  falls back to the opposite direction and reports it; and what the error
  says when nothing is built.

### Modified Capabilities
- `tools/error-boundary`: a new `feature_not_built` category. It is added as
  a separate requirement, so it doesn't collide with the
  `member-not-found-hint-and-stale-script` change, which modifies the
  existing category list.

## Impact

- **COM and adapter code:**
  `src/solidworks_mcp/adapters/solidworks/features.py`
  (`_create_cut_extrude_impl`). It adds no new COM calls, only another
  attempt with one argument changed. All attempts run through
  `_handle_com_operation` on the connect thread.
- **Tools:** `tools/modeling.py` (reply field, message, descriptions) and
  `tools/error_classifier.py` (one rule).
- **Mock adapter:** unchanged. It has no cut implementation, and the tool
  treats a missing `direction_flipped` as false.
- **Tests:**
  - unit tests in `test_features.py`, `test_modeling.py` and
    `test_error_classifier.py`;
  - live tests in `test_live_sw_contributor_fixes.py`,
    `test_live_sw_verify_model.py` and `test_live_sw_cut_extrude_sketch_fix.py`.
- **Order:** depends on PR #192. Closes #193.
