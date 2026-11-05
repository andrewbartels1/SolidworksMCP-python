## Why

The live chamfer and fillet tests (`tests/live/test_live_sw_add_chamfer_tool.py`)
aim at fixed points that assume their test block's height runs along Z. It
runs along Y: the block is sketched on the Top Plane and extruded 15 mm, and
its measured bounding box is min `[0, 0, -30]`, max `[30, 15, 0]` mm. So the
tests chamfer and fillet the wrong faces, and their checks are too loose to
notice. Issue #199.

Measured live during the #195 demo: a 0.5 mm chamfer on `_TOP_FACE`
(`face:0.005,0.005,0.0`) removed 11.08 mm³, which is a 30×15 side face (two
30 mm and two 15 mm edges, about 11.25 mm³). A point on the face the hole
opens onto (`face:0.005,0,-0.025`) removed 17.12 mm³ of an expected 17.29.

| Constant | Meant to be | Actually is |
|---|---|---|
| `_TOP_FACE = "face:0.005,0.005,0.0"` | the 30×30 face with the hole | a 30×15 side face (z = 0) |
| `_BOTTOM_FACE = "face:0.005,0.005,-0.015"` | the opposite 30×30 face | 5 mm inside the block, on no face |
| `_VERTICAL_CORNER_EDGE = "0.0,0.0,-0.0075"` | a vertical corner edge | the midpoint of a 30 mm base edge |

Two further consequences:

- Since #191, a pick must lie within 0.5 mm of an edge or face, so the
  fillet on `_BOTTOM_FACE` now fails instead of filleting anything. The
  chamfer-plus-fillet test can't pass as written.
- The "wrong edge" history in the test's docstring and in
  `_parse_edge_spec`'s docstring (`features.py`) rests on the same wrong
  axes. The edge point `0.01775,0.015,0.0` it describes as "the hole rim"
  is at y = 15, z = 0: exactly on a 30 mm outer edge, far from the hole,
  which opens onto the y = 0 face. The chamfer landed where it was pointed.
  The conclusion that whole-face selection is more robust for the hole rim
  still stands, but the story needs correcting.

The tools behave correctly: each acts on the face or edge its point lies on.
Only the tests and two docstrings are wrong.

## What Changes

- The coupon's face and edge points are worked out from its measured
  bounding box, not hard-coded, so they stay right whichever way the block
  comes out. The coupon builder, the points and the volume formulas move
  to one shared live-test helper, used by the chamfer tests and the API
  lookup demo.
- Every chamfer and fillet test checks the material removed against the
  exact volume for the edges it means to treat, within 0.001 mm³, counting
  each mitred corner once. Only cases with certain geometry are used.
- The calls that must be refused move to their own test file, so a test
  that rightly creates nothing can't be read as a feature demo.
- An entry that selects nothing is logged as one warning line, not a
  traceback. The error returned to the caller is unchanged.
- `live_demo.ps1 -Trace` prints each SolidWorks call with a timestamp, to
  find what makes SolidWorks play its error sound during the run.
- The test module's docstring and `_parse_edge_spec`'s docstring are
  corrected.
- A new spec records what the chamfer and fillet tools do with a face
  point, an edge point and a point on nothing, which the tests then verify.

## Capabilities

### New Capabilities

- `tools/edge-treatment`: how `add_chamfer` and `add_fillet` resolve their
  `edge_names` entries (a face point, an edge point, a name), and how they
  fail when an entry resolves to nothing.

### Modified Capabilities

None.

## Impact

- `tests/live/test_live_sw_add_chamfer_tool.py`: feature tests only,
  points from the measured box, exact volumes, corrected docstring.
- New `tests/live/test_live_sw_edge_pick_refusals.py`: the refusals.
- `tests/live/conftest.py` and `tests/scripts/live_demo.ps1`: the opt-in
  step trace.
- New `tests/live/coupon.py`: the heat-set-insert coupon builder, its face
  and edge points from the bounding box, and the expected-volume formulas.
- `tests/live/test_live_sw_api_lookup.py`: imports the shared helper
  instead of its own `_hole_face`.
- `src/solidworks_mcp/adapters/solidworks/features.py`: `_parse_edge_spec`
  docstring, and `LookupError` for an entry that selects nothing.
- No payload change: the error text returned to callers is the same, only
  how it is logged changes. The live suite is run with the user's
  permission.
