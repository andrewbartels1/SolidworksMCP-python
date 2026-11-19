# Sketching Tools

Build 2-D sketch geometry (lines, circles, arcs, splines, polygons) and apply geometric constraints and driven dimensions. Sketches are the prerequisite for every extrusion, revolve, sweep, and loft feature.

> **Prerequisite:** An active part document with an active sketch edit session.

**Total tools in this category: 19**

---

### `create_sketch`

Open a new sketch on a plane or a flat face of the active part, ready for lines, circles and other sketch entities.

**Prerequisite:** Active part document, no active sketch

**Parameters:** give exactly one of `plane` and `face_point`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `plane` | `str?` | one of | `None` | Sketch plane name (e.g., 'Top', 'Front', 'Right', 'XY', 'XZ', 'YZ', or a plane made by `create_reference_plane`) |
| `face_point` | `list[float]?` | one of | `None` | `[x, y, z]` in mm on a flat face of the body; the sketch opens on that face and moves with it when the model changes |
| `sketch_name` | `str?` | — | `None` | Name `exit_sketch` gives the sketch when it closes it |

A `face_point` that is not on a flat face of the body (in the air, or on a
fillet) fails with `error_type: "invalid_input"` and opens no sketch.

**Sample calls:**

```json
{
  "plane": "Front"
}
```

```json
{
  "face_point": [0, 20, 0]
}
```

**Sample call:**

```json
{"plane": "Top"}
```

---

### `add_line`

Draw a straight line between two points in the open sketch, in mm.

**Prerequisite:** Active sketch edit mode

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `x1` | `float?` | — | `None` | Start point X coordinate in mm |
| `y1` | `float?` | — | `None` | Start point Y coordinate in mm |
| `x2` | `float?` | — | `None` | End point X coordinate in mm |
| `y2` | `float?` | — | `None` | End point Y coordinate in mm |
| `start_x` | `float?` | — | `None` | Start point X alias |
| `start_y` | `float?` | — | `None` | Start point Y alias |
| `end_x` | `float?` | — | `None` | End point X alias |
| `end_y` | `float?` | — | `None` | End point Y alias |
| `construction` | `bool` | — | `False` | Construction geometry flag |

**Sample call:**

```json
{
  "x1": 0.0,
  "y1": 0.0,
  "x2": 80.0,
  "y2": 0.0
}
```

---

### `add_circle`

Draw a circle in the open sketch from its centre and radius, in mm.

**Prerequisite:** Active sketch edit mode

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `center_x` | `float` | ✅ | `` | Circle center X coordinate in mm |
| `center_y` | `float` | ✅ | `` | Circle center Y coordinate in mm |
| `radius` | `float` | ✅ | `` | Circle radius in mm |
| `construction` | `bool` | — | `False` | Construction geometry flag |

**Sample call:**

```json
{
  "center_x": 0.0,
  "center_y": 0.0,
  "radius": 15.0
}
```

---

### `add_rectangle`

Draw a closed, axis-aligned rectangle in the open sketch from two opposite corners, in mm.

**Prerequisite:** Active sketch edit mode

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `x1` | `float?` | — | `None` | First corner X coordinate in mm |
| `y1` | `float?` | — | `None` | First corner Y coordinate in mm |
| `x2` | `float?` | — | `None` | Opposite corner X coordinate in mm |
| `y2` | `float?` | — | `None` | Opposite corner Y coordinate in mm |
| `corner1_x` | `float?` | — | `None` | Corner 1 X alias |
| `corner1_y` | `float?` | — | `None` | Corner 1 Y alias |
| `corner2_x` | `float?` | — | `None` | Corner 2 X alias |
| `corner2_y` | `float?` | — | `None` | Corner 2 Y alias |
| `construction` | `bool` | — | `False` | Construction geometry flag |
| `from_center` | `bool` | — | `False` | `x1`, `y1` is the centre and `x2`, `y2` a corner (`CreateCenterRectangle`) |

**Sample call:**

```json
{
  "x1": -40.0,
  "y1": 0.0,
  "x2": 40.0,
  "y2": 52.0
}
```

---

### `exit_sketch`

Close the open sketch so a feature can use it.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `add_arc`

Draw a circular arc in the open sketch: from its centre, through three points, or tangent.

**Prerequisite:** Active sketch edit mode

**SolidWorks automation note:** `kind` picks the call: `center` is `ISketchManager.CreateArc`, counter-clockwise from start to end; `three_point` is `Create3PointArc` from start to end through `through_x`, `through_y`; `tangent` is `CreateTangentArc` (`swForward`), which starts at the end of an existing entity and leaves tangent to it.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `kind` | `str` | — | `center` | `center`, `three_point` or `tangent` |
| `center_x` | `float?` | for `center` | `None` | Arc center X coordinate in mm |
| `center_y` | `float?` | for `center` | `None` | Arc center Y coordinate in mm |
| `start_x` | `float` | ✅ | `` | Arc start point X coordinate in mm |
| `start_y` | `float` | ✅ | `` | Arc start point Y coordinate in mm |
| `end_x` | `float` | ✅ | `` | Arc end point X coordinate in mm |
| `end_y` | `float` | ✅ | `` | Arc end point Y coordinate in mm |
| `through_x` | `float?` | for `three_point` | `None` | X of a point the arc passes through |
| `through_y` | `float?` | for `three_point` | `None` | Y of a point the arc passes through |

**Sample call:**

```json
{
  "center_x": 0.0,
  "center_y": 0.0,
  "start_x": -30.0,
  "start_y": 0.0,
  "end_x": 30.0,
  "end_y": 0.0
}
```

---

### `add_spline`

Draw a smooth spline through a list of points in the open sketch, in mm.

**Prerequisite:** Active sketch edit mode

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `points` | `List[Dict[str, float]]` | ✅ | `` | List of spline control points with x, y coordinates |

**Sample call:**

```json
{
  "points": [
    {
      "x": 0.0,
      "y": 0.0
    },
    {
      "x": 10.0,
      "y": 15.0
    },
    {
      "x": 20.0,
      "y": 10.0
    }
  ]
}
```

---

### `add_centerline`

Draw a centreline (construction line) in the open sketch, in mm.

**Prerequisite:** Active sketch edit mode

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `x1` | `float?` | — | `None` | Start point X coordinate in mm |
| `y1` | `float?` | — | `None` | Start point Y coordinate in mm |
| `x2` | `float?` | — | `None` | End point X coordinate in mm |
| `y2` | `float?` | — | `None` | End point Y coordinate in mm |
| `start_x` | `float?` | — | `None` | Start point X alias |
| `start_y` | `float?` | — | `None` | Start point Y alias |
| `end_x` | `float?` | — | `None` | End point X alias |
| `end_y` | `float?` | — | `None` | End point Y alias |
| `construction` | `bool` | — | `False` | Construction geometry flag |

**Sample call:**

```json
{
  "x1": 0.0,
  "y1": 0.0,
  "x2": 0.0,
  "y2": 120.0
}
```

---

### `add_polygon`

Draw a regular polygon (e.g. a hexagon) in the open sketch from its centre, radius and number of sides.

`angle` turns it: the degrees its first corner is turned from +x (0 by default), so two hexagons 30° apart make a 12-point opening. A `diameter` dimension (`add_sketch_dimension`) on the polygon's `id` sizes it by the circle drawn inside it, so a hexagon is sized across flats and an equation can drive it.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{"center_x": 0, "center_y": 0, "radius": 6.5, "sides": 6, "angle": 30}
```

---

### `add_ellipse`

Draw an ellipse in the open sketch from its centre and axis lengths, in mm.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `add_sketch_text`

Write text in the open sketch, at a point or centred on one, to deboss or emboss it.

**Prerequisite:** Active sketch edit mode. To read from a face's own side (an underside), open the sketch on that face (`create_sketch` with `face_point`).

**SolidWorks automation note:** `IModelDoc2.InsertSketchText` at the point, with normal letter spacing; the letter height is the text format's `CharHeight`. `center_at` measures the text from its edges (`ISketchText.GetEdges2`) and moves it (`SetCoordinates`) so its middle is on that model point. `$PRP:"name"` in the text shows a custom property: set one to a dimension's name in quotes (`set_custom_property`, value `"D1@Sketch3"`) and the text follows that dimension, through any equation that drives it. On SolidWorks 2026 a line selected first didn't lay the text along it, centre alignment didn't centre it, and mirrored text couldn't be cut, so the tool uses none of them.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | `str` | ✅ | | The text; `$PRP:"name"` shows a custom property |
| `x` | `float` | — | `0` | Start x in mm, sketch coordinates |
| `y` | `float` | — | `0` | Start y (baseline) in mm |
| `height` | `float` | — | `3.5` | Letter height in mm |
| `center_at` | `list[float]?` | — | `None` | Model point `[x, y, z]` in mm for the text's middle |

**Sample call:**

```json
{"text": "solidworksmcp-python $PRP:\"WrenchSize\" mm", "height": 3.5, "center_at": [85, 1.95, 0]}
```

Then `create_cut_extrude` on the sketch with a small `depth` debosses it.

---

### `set_sketch_text`

Rewrite the text in a sketch and rebuild, so debossed lettering shows it.

**Prerequisite:** A part with a sketch holding text from `add_sketch_text`

**SolidWorks automation note:** SolidWorks doesn't redraw sketch text when the model rebuilds, not even a `$PRP:` link to a dimension an equation changed (SolidWorks 2026: four rebuild modes, saving, and writing `ISketchText.Text` outside the sketch all left the old lettering). The tool opens the sketch (`EditSketch`), writes `Text`, closes it and rebuilds; written that way, a `$PRP:` link is read again.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sketch_name` | `str` | ✅ | | The sketch, e.g. `Sketch12` |
| `text` | `str` | ✅ | | The new text; the same `$PRP:"name"` text re-reads the link |

**Sample call:**

```json
{"sketch_name": "Sketch12", "text": "solidworksmcp-python  $PRP:\"WrenchSize\" mm"}
```

---

### `add_sketch_fillet`

Round corners of the open sketch to a radius, picking each corner by its point.

**Prerequisite:** Active sketch edit mode, with entities meeting at each corner

**SolidWorks automation note:** Each corner is found among the open sketch's points (`ISketch.GetSketchPoints2`, within 0.01 mm), selected alone, and rounded with `ISketchManager.CreateFillet` (constrained corners kept, so no dialog opens). The lines either side are trimmed back to the arc, as in SolidWorks. Corners are points, not ids, because a rectangle or polygon registers as one id with no id per corner. Every corner is found before any is rounded: a corner with no sketch point fails as `invalid_input` and nothing changes.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `corners` | `list[list[float]]` | ✅ | | Corners, each `[x, y]` in sketch mm |
| `radius` | `float` | ✅ | | Fillet radius in mm |

**Sample call:**

```json
{"corners": [[-60, -40], [-60, 40]], "radius": 10}
```

---

### `add_sketch_chamfer`

Bevel corners of the open sketch, picking each corner by its point.

**Prerequisite:** Active sketch edit mode, with entities meeting at each corner

**SolidWorks automation note:** Corners are found as for `add_sketch_fillet`, then `ISketchManager.CreateChamfer`: `distance` alone is equal distances (`swSketchChamfer_DistanceEqual`), `distance2` two distances, `angle` a distance and an angle. Giving both `distance2` and `angle` is `invalid_input`.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `corners` | `list[list[float]]` | ✅ | | Corners, each `[x, y]` in sketch mm |
| `distance` | `float` | ✅ | | Distance along each side in mm |
| `distance2` | `float?` | — | `None` | A different distance along the second side, mm |
| `angle` | `float?` | — | `None` | Angle from the first side in degrees, with `distance` |

**Sample call:**

```json
{"corners": [[60, -40], [60, 40]], "distance": 10}
```

---

### `add_slot`

Draw a slot in the open sketch: straight between two centres, or along an arc.

**Prerequisite:** Active sketch edit mode

**SolidWorks automation note:** `ISketchManager.CreateSketchSlot`, length centre to centre, no dimensions added. A straight slot (`swSketchSlotCreationType_line`) runs between its end centres `start` and `end`. An arc slot (`swSketchSlotCreationType_arc`) follows the arc about `center` from `start` to `end`, counter-clockwise. The reply's `area` is the centreline's length times the width plus one circle of the width's diameter (the two rounded ends).

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `kind` | `str` | — | `straight` | `straight`, or `arc` |
| `width` | `float` | ✅ | | Slot width in mm |
| `start` | `list[float]` | ✅ | | `[x, y]` mm: first end centre (straight), or start on the arc (arc) |
| `end` | `list[float]` | ✅ | | `[x, y]` mm: second end centre (straight), or end on the arc (arc) |
| `center` | `list[float]?` | — | `None` | `[x, y]` mm: the arc's centre (arc) |

**Sample call:**

```json
{"start": [-40, -15], "end": [-40, 15], "width": 10}
```

---

### `sketch_trim`

Trim away the piece of a sketch entity at a point, back to where it meets others.

**Prerequisite:** Active sketch edit mode, with an entity at the point

**SolidWorks automation note:** The point is mapped from the sketch into model space (the inverse of `ISketch.ModelToSketchTransform`), the entity there is selected (`SelectByID2`, `SKETCHSEGMENT`), and `ISketchManager.SketchTrim` with `swSketchTrimClosest` removes the piece nearest the point. An entity that meets nothing is removed whole. The reply gives the sketch's segment count before and after; a trimmed entity's id may no longer name a whole segment.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `point` | `list[float]` | ✅ | | `[x, y]` in sketch mm on the piece to remove |

**Sample call:**

```json
{"point": [0, 2]}
```

---

### `sketch_extend`

Lengthen a sketch entity from its end nearest a point until it meets the next entity.

**Prerequisite:** Active sketch edit mode, with an entity at the point and another in its way

**SolidWorks automation note:** The entity at the point is selected as for `sketch_trim`, then `ISketchManager.SketchExtend` lengthens it from the end nearer the point. Nothing at the point, or nothing to reach, fails as `invalid_input` and the sketch is unchanged.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `point` | `list[float]` | ✅ | | `[x, y]` in sketch mm on the entity, near the end to lengthen |

**Sample call:**

```json
{"point": [-3, -0.5]}
```

---

### `set_construction_geometry`

Make sketch entities construction geometry, or normal again, by id.

**Prerequisite:** Active sketch edit mode, with ids from the sketch tools

**SolidWorks automation note:** Sets `ISketchSegment.ConstructionGeometry` on every segment of each id (a rectangle's or polygon's id holds four or more) and reads it back. The property is set, not toggled (`CreateConstructionGeometry` toggles), so a repeated call changes nothing. `construction` on `add_line`, `add_circle` and `add_rectangle` uses this after drawing.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `entities` | `list[str]` | ✅ | | Entity ids, e.g. `Line_3` |
| `construction` | `bool` | — | `True` | `true` for construction geometry, `false` for normal |

**Sample call:**

```json
{"entities": ["Line_3"]}
```

---

### `add_sketch_constraint`

Add a geometric relation between sketch entities: horizontal, vertical, parallel, perpendicular, tangent, coincident, concentric, equal, symmetric, collinear or fix.

**Prerequisite:** Active sketch edit mode with named entities

**SolidWorks automation note:** Implemented via `ISketchRelationManager.AddRelation(entities, swConstraintType_e)`. Entities must be IDs returned from a previous `add_line` / `add_circle` / `add_arc` call (e.g. `"Line_1"`).

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `entity1` | `str` | ✅ | `` | First entity name or ID |
| `entity2` | `str?` | — | `None` | Second entity name or ID (for two-entity relations) |
| `entity3` | `str?` | — | `None` | Third entity name or ID. **Required only for `symmetric`** (the centerline of symmetry, e.g. `"Centerline_5"`); must be `None` for all other relations |
| `relation_type` | `str` | ✅ | `` | One of the supported relation names (see below) |

**Supported `relation_type` values (case-insensitive):**

| Name | Entity arity | Notes |
|------|--------------|-------|
| `horizontal` | 1 or 2 | Line(s) horizontal; with 2 endpoints aligns them horizontally |
| `vertical` | 1 or 2 | Line(s) vertical; with 2 endpoints aligns them vertically |
| `parallel` | 2 | Two lines parallel |
| `perpendicular` | 2 | Two lines at 90° |
| `tangent` | 2 | Line ↔ arc/circle, or arc ↔ arc |
| `coincident` | 2 | Two points (or point on entity) share location |
| `concentric` | 2 | Two arcs/circles share center |
| `equal` | 2 | Equal length (lines) or equal radius (arcs/circles) — maps to `swConstraintType_SAMELENGTH` |
| `symmetric` | 3 | Two entities about a centerline; `entity3` must be the centerline ID returned by `add_centerline` |
| `collinear` | 2 | Two lines on the same infinite line |
| `fix` | 1 | Pin the entity in place |

> **`entity3` is only used by `symmetric`.** All other relation types reject a non-null `entity3` with a clear error.

**Sample call (two-entity perpendicular):**

```json
{
  "entity1": "Line_1",
  "entity2": "Line_2",
  "relation_type": "perpendicular"
}
```

**Sample call (three-entity symmetric):**

```json
{
  "entity1": "Line_1",
  "entity2": "Line_2",
  "entity3": "Centerline_5",
  "relation_type": "symmetric"
}
```

**Sample call (single-entity horizontal):**

```json
{
  "entity1": "Line_1",
  "relation_type": "horizontal"
}
```

**Response shape on success:**

```json
{
  "status": "success",
  "constraint": {
    "id": "Constraint_3",
    "type": "perpendicular",
    "entity1": "Line_1",
    "entity2": "Line_2"
  }
}
```

**Sample call:**

```json
{"entity1": "Line1", "relation_type": "horizontal"}
```

---

### `add_sketch_dimension`

Add a driving dimension to sketch entities: linear, angular, radial or diameter.

**Prerequisite:** Active sketch edit mode

**SolidWorks automation note:** In real SolidWorks sessions, sketch dimension creation can open the interactive `Modify` approval dialog and block unattended runs. The implementation keeps the sketch-input preferences disabled for the full automation session and uses `AddRadialDimension2` or `AddDiameterDimension2` for radial and diameter dimensions so these calls stay non-interactive.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `entity1` | `str` | ✅ | `` | First entity name or ID |
| `entity2` | `str?` | — | `None` | Second entity name or ID (for distance dimensions) |
| `dimension_type` | `str` | — | `linear` | Dimension type (linear, radial, angular, etc.) |
| `value` | `float` | ✅ | `` | Dimension value in mm or degrees |

**Sample call:**

```json
{
  "entity1": "Line_1",
  "value": 50.0
}
```

**Why this is implemented this way:**

- SolidWorks may treat sketch dimension creation like an interactive Smart Dimension workflow unless the sketch-input preferences are suppressed.
- The adapter disables `swInputDimValOnCreate`, `swSketchAcceptNumericInput`, `swSketchCreateDimensionOnlyWhenEntered`, and `swScaleSketchOnFirstDimension` when automation connects, so the tool does not wait for a manual approve click.
- Radial and diameter dimensions use the dedicated `IModelDoc2` APIs instead of the generic extension call because that path is more reliable for circles and arcs in live COM sessions.

---

### `sketch_linear_pattern`

Repeat sketch entities in a straight line at a fixed spacing.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `sketch_circular_pattern`

Repeat sketch entities around the sketch origin, e.g. a bolt circle.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `sketch_mirror`

Mirror sketch entities about a centreline in the open sketch.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `sketch_offset`

Offset sketch entities by a distance in mm, outward or inward, e.g. for a wall or a clearance.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `sketch_convert_entities`

Copy model edges, or a face's whole outline, into the open sketch (Convert Entities).

**Prerequisite:** Active sketch edit mode, on a part with those edges.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `edge_points` | `list[list[float]]` | one of | `[]` | `[x, y, z]` mm on each model edge to copy |
| `face_point` | `list[float]` | one of | `None` | `[x, y, z]` mm on a face whose outline to copy |
| `construction` | `bool` | — | `false` | Make the copies construction geometry |

**Sample call:**

```json
{"face_point": [0, 0, 20]}
```

---

### `sketch_tutorial_simple_hole`

> **Deprecated:** no replacement; build the hole with the sketching and feature tools. It keeps working until 3.0.0, when it is removed.

Demonstrate the sketch steps: draw a 5 mm circle at the origin on the Top plane and close the sketch.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

---

### `check_sketch_fully_defined`

Check whether a sketch is fully defined, under-defined or over-defined.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sketch_name` | `str?` | — | `null` | Optional sketch name. If omitted, checks the active or last sketch. |

**Sample call:**

```json
{}
```
