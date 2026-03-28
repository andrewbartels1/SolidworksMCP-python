# Sketching Tools

Build 2-D sketch geometry (lines, circles, arcs, splines, polygons) and apply geometric constraints and driven dimensions. Sketches are the prerequisite for every extrusion, revolve, sweep, and loft feature.

> **Prerequisite:** An active part document with an active sketch edit session.

**Total tools in this category: 18**

---

### `create_sketch`

Create a new sketch on the specified plane.

**Prerequisite:** Active part document, no active sketch

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `plane` | `str` | ✅ | `` | Sketch plane name (e.g., 'Top', 'Front', 'Right', 'XY', 'XZ', 'YZ') |
| `sketch_name` | `str?` | — | `None` | Sketch name alias |

**Sample call:**

```json
{
  "plane": "Front"
}
```

---

### `add_line`

Add a line to the current sketch.

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
{}
```

---

### `add_circle`

Add a circle to the current sketch.

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

Add a rectangle to the current sketch.

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

**Sample call:**

```json
{}
```

---

### `exit_sketch`

Exit sketch editing mode.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `add_arc`

Add an arc to the current sketch.

**Prerequisite:** Active sketch edit mode

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `center_x` | `float` | ✅ | `` | Arc center X coordinate in mm |
| `center_y` | `float` | ✅ | `` | Arc center Y coordinate in mm |
| `start_x` | `float` | ✅ | `` | Arc start point X coordinate in mm |
| `start_y` | `float` | ✅ | `` | Arc start point Y coordinate in mm |
| `end_x` | `float` | ✅ | `` | Arc end point X coordinate in mm |
| `end_y` | `float` | ✅ | `` | Arc end point Y coordinate in mm |

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

Add a spline curve to the current sketch.

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

Add a centerline to the current sketch.

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
{}
```

---

### `add_polygon`

Add a regular polygon to the current sketch.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `add_ellipse`

Add an ellipse to the current sketch.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `add_sketch_constraint`

Add a geometric constraint/relation between sketch entities.

**Prerequisite:** Active sketch edit mode with named entities

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `entity1` | `str` | ✅ | `` | First entity name or ID |
| `entity2` | `str?` | — | `None` | Second entity name or ID (if required) |
| `relation_type` | `str` | ✅ | `` | Relation type (parallel, perpendicular, tangent, coincident, etc.) |

**Sample call:**

```json
{
  "entity1": "Line1",
  "relation_type": "perpendicular"
}
```

---

### `add_sketch_dimension`

Add a dimension to sketch entities.

**Prerequisite:** Active sketch edit mode

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
  "entity1": "Line1",
  "value": 50.0
}
```

---

### `sketch_linear_pattern`

Create a linear pattern of sketch entities.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `sketch_circular_pattern`

Create a circular pattern of sketch entities.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `sketch_mirror`

Mirror sketch entities about a centerline.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `sketch_offset`

Create an offset of sketch entities.

**Prerequisite:** Active sketch edit mode

**Sample call:**

```json
{}
```

---

### `sketch_tutorial_simple_hole`

Tutorial: Create a simple circular hole sketch.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `tutorial_simple_hole`

Create a simple hole as a guided tutorial workflow.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `plane` | `str` | ✅ | `` | Sketch plane for the hole |
| `center_x` | `float` | ✅ | `` | Hole center X coordinate in mm |
| `center_y` | `float` | ✅ | `` | Hole center Y coordinate in mm |
| `diameter` | `float` | ✅ | `` | Hole diameter in mm |
| `depth` | `float?` | — | `None` | Hole depth in mm (None for through hole) |

**Sample call:**

```json
{
  "plane": "Front",
  "center_x": 0.0,
  "center_y": 0.0,
  "diameter": 10.0
}
```

---
