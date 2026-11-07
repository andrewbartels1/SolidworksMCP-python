## Context

The coupon (`_heat_insert_coupon`) is a 30×30 mm square sketched on the
Top Plane, extruded 15 mm, with a Ø5.5 mm hole sketched on the Top Plane
and cut 6 mm deep. Measured live: bounding box min `[0, 0, -30]`, max
`[30, 15, 0]` mm. So, in model mm:

- Height runs along Y. The sketch face, which the hole opens onto, is
  y = 0; the opposite face is y = 15.
- The hole's centre is at (15, 0, −15).
- The four side faces are x = 0, x = 30, z = 0 and z = −30, each 30×15.
- The vertical (15 mm) corner edges run along Y at the four corners, e.g.
  x = 0, z = 0.

Point picks resolve by true closest distance and must lie within 0.5 mm of
the face or edge (`_PICK_TOLERANCE_M`, since #191).

## Goals / Non-Goals

**Goals:**

- Every live chamfer and fillet test treats the face or edge it names, and
  fails if the tool treats another.
- One shared coupon helper, so the chamfer tests and the API lookup demo
  can't drift apart again.

**Non-Goals:**

- Changing the chamfer or fillet tools; they behave correctly.
- Fixing the old coordinate-only edge picking described in `features.py`
  beyond its docstring.

## Decisions

### 1. Points come from the measured bounding box

`tests/live/coupon.py` holds:

- `build(adapter)`: the coupon builder, moved from the test module, which
  returns the measured coupon;
- `Coupon.measure(adapter)`: reads `get_model_geometry_summary()`;
- points derived from the box: `hole_face`, `side_face`, `opposite_edge`
  (halfway along a 30 mm edge of the face opposite the hole) and `inside`
  (5 mm inside the block, on no face);
- `add_chamfer_tool`, `feature_names` and `volume`, shared by both test
  files.

The height axis is the axis whose size is 15 mm. The hole face is the end
of that axis at the sketch plane (the end nearer 0). Face points sit 5 mm
in from a corner, well clear of the hole at the face's centre.

*Alternative considered:* hard-code the corrected Y-up points. They are
right today, but they would fail silently again if the builder or a
SolidWorks default changed the orientation.

### 2. Exact volumes, only where the geometry is certain

The first live run used a window of 90 % to 100 % of the plain sum of the
edges. That was too loose: it would pass a result several mm³ off. The
measured values pinned the true shape instead:

| Case | Measured | Plain sum | Exact, corners once |
|---|---|---|---|
| Hole face, 0.5 mm chamfer | 17.124 | 17.291 | 17.1241 |
| Side face, 0.5 mm chamfer | 11.083 | 11.250 | 11.0833 |
| Hole face + vertical corner edge | 18.957 | 19.166 | 18.947 |
| Opposite face, 1 mm fillet | 25.266 | 25.752 | 25.369 |

Two chamfers meeting at a square corner mitre there, so the corner's
`w³/3` is removed once (`coupon.chamfer_corner_overlap`). With it, the two
single-face chamfers match to 0.0001 mm³. Where three chamfers meet at one
corner, and where fillets meet, SolidWorks' corner differs from the simple
model (0.010 and 0.103 mm³), so those cases are not used. Instead:

- the face-plus-edge test uses an edge on the opposite face, which shares
  no corner with the hole face (17.1241 + 3.75 mm³);
- the fillet test fillets one 30 mm edge on its own: (1 − π/4)·30 =
  6.4381 mm³.

Every test asserts the exact value within 0.001 mm³
(`coupon.VOLUME_TOLERANCE_MM3`), and prints measured, exact and the
difference.

### 3. Refusals live in their own file

The calls that must be refused (a bad edge name, a good entry with a bad
one, a point inside the block) move to `test_live_sw_edge_pick_refusals.py`.
Mixed in with the feature tests, a test that correctly creates nothing
read like a feature demo that had silently failed. Each refusal checks the
error text and that the part is unchanged (no feature, same volume), and
its evidence line says "Refused, as it should be".

### 4. Docstrings tell the true story

The test module's docstring and `_parse_edge_spec`'s docstring said an
edge pick aimed at the hole rim landed on a 30 mm outer edge. With the
real axes, the point used (`0.01775, 0.015, 0.0`) is on that outer edge,
so the pick did what it was told. Both docstrings now say so.

### 5. An entry that selects nothing is logged as one warning

`_add_chamfer_impl` and `_add_fillet_impl` raised a plain `Exception`
("Failed to select edge: ...") when an entry selected nothing, so
`_handle_com_operation` logged it as a fault with a full traceback. It is
an expected answer, like the pick-tolerance `LookupError`, so it now raises
`LookupError` and is logged as one warning line. The returned error text is
unchanged.

### 6. A step trace for SolidWorks' error sound

SolidWorks played its error sound ("bonk") during the live run, and
nothing in the code shows a dialog. `live_demo.ps1 -Trace` sets
`SW_DEMO_TRACE`, and the live `conftest.py` then prints every adapter call
with a timestamp as it starts and ends, plus the document drain between
tests. Matching the sound to a line finds the call; the fix follows from
that. Test harness only; the server is unchanged.

## Risks / Trade-offs

- [The 0.001 mm³ tolerance is too tight for SolidWorks' volume] → the two
  single-face chamfers already matched to 0.0001 mm³. If the single-edge
  fillet misses, that is itself the finding (SolidWorks' fillet volume is
  approximate), and it is reported, not absorbed.
- [Three-chamfer and fillet corners are no longer covered] → they test
  SolidWorks' corner construction, not the edge pick, which is what these
  tests are for.
