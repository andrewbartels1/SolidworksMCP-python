## Context

Sketch tools live in `adapters/solidworks/sketch.py` (one `_<tool>_impl`
per tool, run through `_handle_com_operation`) and `tools/sketching.py`
(the inputs and the tools). Entities are registered in
`adapter._sketch_entities` under ids such as `Line_1`; a rectangle or
polygon registers as one id holding its segments. Coordinates are sketch
coordinates in mm. `_to_sketch_space` already maps a model point into the
open sketch with the sketch's `ModelToSketchTransform`.

The COM signatures and enum values below were read from this machine's
SolidWorks 2026 type library (`lookup_api_method`, `get_api_enum`).

## Goals / Non-Goals

**Goals:** the sketch operations agents need next, each one tool call with
the arguments an agent already has (the points and ids it drew); construction
geometry that works on SolidWorks.

**Non-goals:** 3D sketches, sketch blocks, splines by equation, conics and
the other `ISketchManager` members; selecting a slot as a pattern or mirror
seed (a later item if needed).

## Decisions

### 1. Corners are picked by point, not by entity id

A rectangle or polygon registers as one id, so there is no id for "the
top-left corner". The agent does know the corner's coordinates: it drew
them. `add_sketch_fillet` and `add_sketch_chamfer` take `corners`, a list of
`[x, y]` in sketch mm, and find the open sketch's point at each
(`ISketch.GetSketchPoints2`, X and Y within 0.01 mm). Each corner is
selected alone (`ISketchPoint.Select4`) and filleted or chamfered by its own
call, so each gets its own id in the reply. A corner with no sketch point
fails as `invalid_input` naming it, before anything changes.

`CreateFillet(Radius, ConstrainedCorners)`: `ConstrainedCorners` is
`swConstrainedCornerKeepGeometry` (1). `swConstrainedCornerInteract` (0)
can open a dialog, which stalls an automated run.

`CreateChamfer(Type, Distance, AngleORdist)`, `swSketchChamferType_e`:
`distance` alone is equal distances (2); with `distance2`, two distances
(1); with `angle` (degrees), distance and angle (0). Giving both
`distance2` and `angle` is `invalid_input`.

Alternative considered: two entity ids per corner. Rejected: it can't
name a rectangle's corners and makes the agent find ids it never saw.

### 2. Slots

`CreateSketchSlot(SlotCreationType, SlotLengthType, Width, X1..Z3,
CenterArcDirection, AddDimension)`, length type
`swSketchSlotLengthType_CenterCenter` (0), no dimensions added:

- `kind: "straight"`: `swSketchSlotCreationType_line` (0), point 1 and 2 the
  arc centres (`start`, `end`), point 3 the end again.
- `kind: "arc"`: `swSketchSlotCreationType_arc` (2), point 1 the arc's
  centre (`center`), 2 and 3 the slot's centreline start and end;
  `CenterArcDirection` 1, counter-clockwise from start to end.

Which point is which, and the direction's sign, are taken from the API
help and checked in the live demo, whose cut volume would differ if they
were wrong. The reply gives the id, the centres, the width and the area
(straight: `length * width + pi * (width / 2) ** 2`; arc: the centreline arc
length times width plus the same end circles).

### 3. Trim and extend at a point

`SketchTrim(Option, X, Y, Z)` and `SketchExtend(X, Y, Z)` take a pick point
in **model** space (recorded macros pass model coordinates), with the entity
selected first. The tools take `point`, `[x, y]` in sketch mm, as every other
sketch tool does. A new `_to_model_space` maps it through the inverse of
`ModelToSketchTransform`; the entity under it is selected with
`SelectByID2("", "SKETCHSEGMENT", ...)` (a null `VT_DISPATCH` callout,
runbook item 11), then `SketchTrim(swSketchTrimClosest (0), ...)` removes the
piece nearest the point, back to the nearest intersections, or
`SketchExtend` lengthens the entity from its end nearest the point to the
next entity it meets. `False` from either, or nothing under the point, fails
as `invalid_input` and the sketch is unchanged.

The reply gives the sketch's segment count before and after. A trimmed
entity's id may name a segment SolidWorks has split or deleted; the reply
says so instead of guessing new ids.

### 4. Construction geometry by property

`set_construction_geometry(entities, construction=True)` sets
`ISketchSegment.ConstructionGeometry` on each segment of each id, then reads
it back. Setting the property is idempotent; the toggle
`CreateConstructionGeometry` would flip entities already set. An unknown id
fails before anything changes.

The `construction` fix reuses it: after `add_line`, `add_circle` or
`add_rectangle` draws with `construction` on, the tool calls
`set_construction_geometry` on the new id. It sits in the tool, not in each
adapter method, so every adapter gets it with no signature change.

### 5. `add_arc` kinds and `add_rectangle` `from_center`

- `add_arc` `kind`: `center` (default; `CreateArc`, today), `three_point`
  (`start`, `end` and `through_x`/`through_y`; `Create3PointArc`), `tangent`
  (`start` must be the end of an existing entity, `end` where the arc ends;
  `CreateTangentArc(..., swForward (1))`). `center_*` is required only for
  `center`, `through_*` only for `three_point`; a missing field is
  `invalid_input`.
- `add_rectangle` `from_center`: `x1`, `y1` the centre, `x2`, `y2` a corner
  (`CreateCenterRectangle`). The reply's `corner1`/`corner2` are the real
  opposite corners and `width`/`height` the full size, so it reads the same
  as a corner rectangle.

### 6. Where the code goes

The new COM code goes in `adapters/solidworks/sketch.py`, already 2,900
lines. Splitting it is queue item 40 (structure review); this change adds
its functions at the end in one block and doesn't reorganise the file.
Each new adapter method is added to `base.py`, `circuit_breaker.py`,
`connection_pool.py` and the mock, as today. Item 40 will look at
replacing those per-method forwards with one path.

## Risks / Trade-offs

- [Slot point order or arc direction differs from the help] → the live
  demo's volume check catches it; fix and rerun before sign-off.
- [Pick points in model space are wrong for a sketch not on the Front
  plane] → the demo's sketches are on the Top plane, where sketch Y is model
  -Z, so a wrong mapping fails there.
- [A corner point shared by several entities, e.g. a polygon vertex on a
  construction line] → the fillet uses SolidWorks' own choice of the two
  segments at that point, the same as clicking it.
