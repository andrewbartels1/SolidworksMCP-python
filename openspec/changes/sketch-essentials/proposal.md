## Why

An agent can draw lines, arcs, circles, rectangles and polygons, but not the
sketch operations almost every real part needs next: a rounded or bevelled
corner, a slot, trimming a profile back to where two shapes meet, or turning
a line into construction geometry. Without them an agent fakes a rounded
corner from lines and a hand-placed arc, then fights the dimensions, and a
slot takes six entities. This is the first of the COM-coverage packages
(queue item 32, the user's choice 2026-11-19): it fills the gaps in
`ISketchManager` an agent hits first.

It also fixes a fault found while planning: `add_line`, `add_circle` and
`add_rectangle` accept `construction`, but on SolidWorks the flag is dropped
and the reply still says `"construction": true`. Only the mock honours it.

## What Changes

- **`add_sketch_fillet`**: rounds sketch corners, picked by their points in
  sketch coordinates, to a radius (`ISketchManager.CreateFillet`). The
  lines either side are trimmed back, as in SolidWorks.
- **`add_sketch_chamfer`**: bevels sketch corners picked the same way: an
  equal distance, two distances, or a distance and an angle
  (`CreateChamfer`).
- **`add_slot`**: a straight slot from its two arc centres and width, or an
  arc slot from a centre, start and end and width (`CreateSketchSlot`).
  Returns one id for the slot, with its centres, width and area.
- **`sketch_trim`** and **`sketch_extend`**: trim the piece of an entity
  nearest a point back to where it meets other geometry, or extend an
  entity from the end nearest a point to the next geometry it meets
  (`SketchTrim`, `SketchExtend`).
- **`set_construction_geometry`**: makes sketch entities construction
  geometry, or normal again, by id (`ISketchSegment.ConstructionGeometry`).
- **`add_arc`** gains `kind`: `center` (today's, the default),
  `three_point` (start, end and a point the arc passes through,
  `Create3PointArc`) and `tangent` (from the end of the last entity, tangent
  to it, `CreateTangentArc`).
- **`add_rectangle`** gains `from_center`: the first point is the centre and
  the second a corner (`CreateCenterRectangle`).
- **Fix:** `construction` on `add_line`, `add_circle` and `add_rectangle`
  makes construction geometry on SolidWorks, as the reply already says.
- Six new tools: 145 to 151.

## Capabilities

### New Capabilities

- `tools/sketch-corners`: `add_sketch_fillet` and `add_sketch_chamfer`
  round or bevel sketch corners picked by point.
- `tools/sketch-slots`: `add_slot` draws a straight or arc slot.
- `tools/sketch-trim-extend`: `sketch_trim` and `sketch_extend` cut back
  or lengthen sketch entities at a point.
- `tools/sketch-construction`: `set_construction_geometry`, and
  `construction` honoured on `add_line`, `add_circle` and `add_rectangle`.
- `tools/sketch-arcs-and-rectangles`: `add_arc` `kind` (centre,
  three-point, tangent) and `add_rectangle` `from_center`.

### Modified Capabilities

None. No existing spec covers the basic sketch tools; the two changed tools
keep their current behaviour by default.

## Impact

- `adapters/solidworks/sketch.py` (the COM calls), `adapters/base.py`,
  `circuit_breaker.py`, `connection_pool.py`, `mock_adapter.py` (the new
  methods), `tools/sketching.py` (inputs and tools), `tools/tool_hints.py`,
  `tools/support_levels.py`, the toolset table.
- Docs: the sketching catalog page, tool counts (README, index, catalog
  index, tools overview), progress files, `llms.txt`, CHANGELOG.
- A live demo, `tests/live/test_live_sw_sketch_essentials.py`, recorded as
  a GIF: one part built with every new operation, its volume checked
  against the hand calculation.
- No new dependency. No breaking change: both changed tools default to
  today's behaviour.
