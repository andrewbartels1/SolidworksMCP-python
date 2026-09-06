# Modeling Tools

Create and manipulate SolidWorks parts, assemblies, and drawings. These are the foundational tools for any CAD workflow — opening files, creating features (extrude, revolve), and querying/setting driven dimensions.

> **Prerequisite:** An active SolidWorks session. Most feature tools require an open Part document.

**Total tools in this category: 12**

---

### `open_model`

Open a SolidWorks model (part, assembly, or drawing).

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str` | ✅ | `` | Full path to the SolidWorks file (.sldprt, .sldasm, .slddrw) |

**Sample call:**

```json
{
  "file_path": "C:\\Temp\\mcp_demo\\part.sldprt"
}
```

---

### `create_part`

Create a new SolidWorks part document.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | ✅ | `` | Name for the new part |
| `template` | `str?` | — | `None` | Template file path for the new part |
| `units` | `str?` | — | `None` | Document units |
| `material` | `str?` | — | `None` | Material name |

**Sample call:**

```json
{
  "name": "MCP_Demo_Part"
}
```

---

### `create_assembly`

Create a new SolidWorks assembly document.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | ✅ | `` | Name for the new assembly |
| `template` | `str?` | — | `None` | Assembly template file path |
| `components` | `List[str]` | ✅ | `` | Component list |

**Sample call:**

```json
{
  "name": "MCP_Demo_Part",
  "components": []
}
```

---

### `create_drawing`

Create a new SolidWorks drawing document.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | ✅ | `` | Name for the new drawing |
| `template` | `str?` | — | `None` | Drawing template file path |
| `model_path` | `str?` | — | `None` | Source model path |
| `sheet_format` | `str?` | — | `None` | Sheet format template |

**Sample call:**

```json
{
  "name": "MCP_Demo_Part"
}
```

---

### `close_model`

Close the current SolidWorks model.

**Prerequisite:** An active open document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `save` | `bool` | — | `False` | Save the model before closing |

**Sample call:**

```json
{}
```

---

### `create_extrusion`

Create an extrusion feature from the active sketch.

**Prerequisite:** Active part with an active sketch (exit sketch first with exit_sketch)

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sketch_name` | `str` | ✅ | `` | Sketch name to extrude |
| `depth` | `float` | ✅ | `` | Extrusion depth in millimeters |
| `direction` | `str` | — | `blind` | Extrusion direction |
| `reverse` | `bool?` | — | `None` | Reverse direction alias |
| `draft_angle` | `float` | — | `0.0` | Draft angle in degrees |
| `reverse_direction` | `bool` | — | `False` | Reverse extrusion direction |
| `both_directions` | `bool` | — | `False` | Extrude in both directions |
| `thin_feature` | `bool` | — | `False` | Create as thin wall feature |
| `thin_thickness` | `float?` | — | `None` | Thickness for thin wall feature in mm |
| `end_condition` | `str` | — | `Blind` | End condition type |
| `merge_result` | `bool` | — | `True` | Merge with existing geometry |

**Sample call:**

```json
{
  "sketch_name": "Sketch1",
  "depth": 25.0
}
```

---

### `create_revolve`

Create a revolve feature from the active sketch.

**Prerequisite:** Active part with an active sketch containing the profile and axis

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sketch_name` | `str` | ✅ | `` | Sketch name to revolve |
| `axis_entity` | `str` | ✅ | `` | Axis entity for the revolve |
| `angle` | `float` | ✅ | `` | Revolve angle in degrees |
| `direction` | `str` | — | `one_direction` | Revolve direction |
| `reverse_direction` | `bool` | — | `False` | Reverse revolve direction |
| `both_directions` | `bool` | — | `False` | Revolve in both directions |
| `thin_feature` | `bool` | — | `False` | Create as thin wall feature |
| `thin_thickness` | `float?` | — | `None` | Thickness for thin wall feature in mm |
| `merge_result` | `bool` | — | `True` | Merge with existing geometry |

**Sample call:**

```json
{
  "sketch_name": "Sketch1",
  "axis_entity": "Line1",
  "angle": 360.0
}
```

---

### `get_dimension`

Get the value of a dimension from the current model.

**Prerequisite:** Active document with named dimensions

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str?` | — | `None` | Dimension name (e.g., 'D1@Sketch1', 'D1@Boss-Extrude1') |
| `dimension_name` | `str?` | — | `None` | Dimension name alias |

**Sample call:**

```json
{}
```

---

### `set_dimension`

Set the value of a dimension in the current model.

**Prerequisite:** Active document with named dimensions

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str?` | — | `None` | Dimension name (e.g., 'D1@Sketch1', 'D1@Boss-Extrude1') |
| `dimension_name` | `str?` | — | `None` | Dimension name alias |
| `value` | `float` | ✅ | `` | New dimension value in millimeters |
| `units` | `str?` | — | `None` | Units alias |

**Sample call:**

```json
{
  "value": 50.0
}
```

---

### `set_units`

Set the active document's linear unit system (`mm`, `cm`, `m`, `in`, `ft`; aliases such as `inch` / `millimeters` accepted). The setting is applied and read back — a mismatch is reported as an error rather than a false success.

**Prerequisite:** Active document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `unit_system` | `str` | ✅ | `` | Linear unit system: mm, cm, m, in, or ft |

**Sample call:**

```json
{
  "unit_system": "in"
}
```

---

### `rename_feature`

Rename a feature on the feature tree. SolidWorks silently refuses a rename onto a name another feature already uses, so the new name is read back and a mismatch is reported as an error. Renaming a feature to its current name is a no-op success.

**Prerequisite:** Active document containing the named feature

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `old_name` | `str` | ✅ | `` | Current feature name, e.g. 'Fillet1' |
| `new_name` | `str` | ✅ | `` | New feature name, e.g. 'MountingEdgeFillet' |

**Sample call:**

```json
{
  "old_name": "Fillet1",
  "new_name": "EdgeBreak"
}
```

---

### `create_reference_point`

Create a reference point on the active part. Two modes: `along_curve` places a point on the edge under `(x, y, z)` mm — either `distance` mm from the edge start or at `percent` (0–100) of its length; `face_center` places a point at the centroid of the face under `(x, y, z)` mm. The coordinate must lie on the target edge/face. `InsertReferencePoint` always returns a feature, so success is confirmed by the feature tree growing.

**Prerequisite:** Active part with the target edge/face

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `mode` | `str` | ✅ | `` | `along_curve` or `face_center` |
| `x` | `float` | ✅ | `` | X of a point on the target edge/face, in mm |
| `y` | `float` | ✅ | `` | Y of a point on the target edge/face, in mm |
| `z` | `float` | ✅ | `` | Z of a point on the target edge/face, in mm |
| `distance` | `float?` | — | `None` | along_curve only: offset from the edge start in mm |
| `percent` | `float?` | — | `None` | along_curve only: 0–100 of the edge length |

**Sample call:**

```json
{
  "mode": "along_curve",
  "x": 25, "y": 0, "z": 10,
  "percent": 50
}
```

---
