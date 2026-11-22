## Context

`create_sweep` (`IFeatureManager.InsertProtrusionSwept4`) adds material
along a path; it picks the profile as "the sketch closed last that isn't the
path", returns a `SolidWorksFeature`, and doesn't measure anything. A
helix exists only in a live regression test, made with a raw
`IModelDoc2.InsertHelix` call on an open sketch holding a circle; it returns
nothing, so the test reads the helix's name back from the tree.

## Goals / Non-Goals

**Goals:** a helix (and a flat spiral) tool whose reply says where the helix
starts; a cut sweep; a named or circular profile for both sweeps; both
sweeps measured by volume, as the newer feature tools are.

**Non-Goals:** thicken (no surfaces yet); variable-pitch helices; guide
curves for sweeps; a dedicated spring or thread tool (the demo builds both
from the general tools).

## Decisions

### 1. `create_helix`

- Inputs: `sketch_name` (one circle), `defined_by` (`height_and_pitch`,
  `height_and_revolutions`, `pitch_and_revolutions`, `spiral`), `height`,
  `pitch`, `revolutions` (each > 0, the two `defined_by` names required),
  `clockwise` (false), `reverse` (false), `start_angle` (0), `taper_angle`
  (none) and `taper_outward` (false).
- The base sketch is checked first: its segments must be exactly one arc
  that is a full circle (`ISketchArc.IsCircle`). The diameter is the
  circle's length / pi; the centre comes from `GetCenterPoint2`, turned into
  model mm with the sketch's transform.
- The sketch is selected and `IModelDoc2.InsertHelix(reverse, clockwise,
  tapered, outward, defined_by, height m, pitch m, revolutions, taper rad,
  start rad)` is called (`swHelixDefinedBy_e`: pitch and revolution 0,
  height and revolution 1, height and pitch 2, spiral 3). It returns
  nothing, so the new feature is found by comparing the tree's names before
  and after (as `create_axis` does), preferring a `Helix` type; none means
  an error, and nothing is left behind.
- The missing one of height, pitch and revolutions is worked out (height =
  pitch x revolutions). The length is revolutions x sqrt((pi D)^2 + p^2) for
  a straight helix; a spiral's is the sum of its circles, pi x n x (D + n p);
  a tapered helix uses the mean diameter. The reply says the length is
  worked out, not measured.
- The start point is the circle's centre plus the radius along the sketch's
  start direction turned by `start_angle`, in model mm.

### 2. Sweeps

- `SweepParameters` gains `profile` and `circular_profile_diameter`. The
  profile choice (circle, named sketch, closed last) is one helper both
  sweeps use; a `profile` that is the path, or no profile at all, is
  `invalid_input` naming the sketches found.
- `create_sweep` keeps `InsertProtrusionSwept4`; `create_cut_sweep` calls
  `InsertCutSwept5` with the same arguments (plus the assembly-scope ones,
  off). With `circular_profile_diameter` only the path is selected (mark
  4) and `CircularProfile` is on with the diameter in metres; otherwise the
  profile is selected under mark 1 and the path under mark 4, as today.
- Both run through the measured-feature path (`_measured`): the volume
  before and after, an unchanged sweep deleted and reported, rebuild errors
  reported. `create_sweep` must grow the volume and `create_cut_sweep` must
  shrink it. Both keep returning a `SolidWorksFeature`, the measurements in
  its `parameters`.
- The sweep code moves from `features.py` into a new
  `adapters/solidworks/swept.py` with the helix (queue item 40: a module per
  topic).

### 3. What the live demo has to settle

Four details are unknown until SolidWorks runs them, and a short probe
settles them before the build:

1. Does `InsertHelix` take a **closed, selected** sketch (the tool's flow),
   or only an open one, as the regression test uses?
2. Where does a helix start at `start_angle` 0, relative to the sketch's
   axes (the regression test's helix on the Top plane started at
   (r, 0, 0))?
3. Does `InsertCutSwept5` take the same marks (profile 1, path 4)?
4. Does `CircularProfile` sweep a circle with only the path selected?

### 4. The demo's arithmetic

A profile in a plane that contains the helix's axis, swept along the helix,
sweeps the same volume as a turn about the axis per revolution: V = A x 2
pi x r_c x n, where A is the profile's area and r_c its centroid's distance
from the axis (Pappus). A 2 mm wire on a 20 mm helix of 8 turns is
pi x 1^2 x 2 pi x 10 x 8 = 1,579.14 mm^3. A thread cut is checked the same
way, over the turns that lie wholly inside the rod.

## Risks / Trade-offs

- [The helix starts somewhere else, so the profile misses the path] → the
  start point is checked by the probe and the demo; the reply gives it so
  an agent never has to guess.
- [A cut sweep's profile only partly overlaps the solid] → the volume is
  measured, not worked out; the demo checks against the hand calculation.
- [Moving the sweep code breaks imports] → the tests that import it move
  with it; the tool and adapter method names don't change.
