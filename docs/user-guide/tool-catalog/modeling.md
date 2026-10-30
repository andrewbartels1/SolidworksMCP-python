# Modeling Tools

Create and manipulate SolidWorks parts, assemblies, and drawings. These are the foundational tools for any CAD workflow — opening files, creating features (extrude, revolve), and querying/setting driven dimensions.

> **Prerequisite:** An active SolidWorks session. Most feature tools require an open Part document.

**Total tools in this category: 12**

## Measured change

`create_extrusion`, `create_revolve` and `create_cut_extrude` report what the feature
actually did. Their success reply carries a `measured_change` block with
`volume_before_mm3`, `volume_after_mm3` and `volume_delta_mm3`; the bounding-box size
before and after; and the solid-body count before and after. If the feature reports
success but the volume did not change, the reply also has a `warning`: that is how
SolidWorks shows a feature it accepted without doing anything. Measuring never fails
the feature; any value that can't be read is `null` with a `note`. Finish a build with
`verify_model` (see [Analysis tools](analysis.md)).

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

### `select_feature`

Select a named feature, sketch, reference plane or assembly component. Replaces the current selection by default; `append: true` adds to it. A name that cannot be selected is an **error** naming it — never a success with `selected: false`. The response reports the name actually matched and how many entities are now selected.

**Prerequisite:** Active document containing the named entity

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `feature_name` | `str` | ✅ | `` | Feature, sketch, plane or component name, e.g. 'Boss-Extrude1', 'Sketch1', 'Front Plane' (an '@Part1' suffix is ok) |
| `append` | `bool` | ❌ | `false` | Add to the current selection instead of replacing it |

**Sample call:**

```json
{
  "feature_name": "Boss-Extrude1"
}
```

---

### `select_face_edges`

Multi-select every edge bounding one face of the active part. Identify the face with **exactly one** of `point` (a point on the face, mm), `side` (the furthest flat face facing `top`/`bottom`/`front`/`back`/`right`/`left` or `+X`…`-Z`; top=+Y, front=+Z, right=+X as in SolidWorks' default views) or `plane` (a reference plane name — the body face lying on it). `edge_type` narrows to `linear` or `circular` edges (e.g. hole rims).

The edges become the live selection, so a following `add_chamfer` / `add_fillet` with an empty `edge_names` acts on exactly them. Anything that changes the selection in between — including a click in SolidWorks — changes what is used. The response reports the face chosen (`data.face`: centre, normal, area) and each edge (`data.edges`: curve type, endpoints/length or centre/radius), so you can switch to `point` if `side` picked a different face than intended.

**Prerequisite:** Active part document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `point` | `list[float]` | ❌ | `null` | A point on the face, `[x, y, z]` in mm |
| `side` | `str` | ❌ | `null` | `+X`/`-X`/`+Y`/`-Y`/`+Z`/`-Z` or `right`/`left`/`top`/`bottom`/`front`/`back` |
| `plane` | `str` | ❌ | `null` | Reference plane name, e.g. 'Front Plane' |
| `edge_type` | `str` | ❌ | `all` | `all`, `linear` or `circular` |
| `append` | `bool` | ❌ | `false` | Add to the current selection instead of replacing it |

**Sample call** (then chamfer the selected hole rims with `add_chamfer({"distance": 0.5, "edge_names": []})`):

```json
{
  "side": "top",
  "edge_type": "circular"
}
```

---

### `rebuild_model`

Force a rebuild of the active model and report exactly what is wrong. When features fail, the response is an **error** whose `data.errors` lists each failing feature with its `type`, SolidWorks error `code` and `code_name` (`swFeatureError_e`), `severity`, a `description`, the `parents` it depends on (sketches report their segment count, so an emptied sketch is called out), and a concrete `hint` for fixing it. Warnings alone still succeed and are listed. Use after `set_dimension` or other programmatic edits.

**Prerequisite:** Active document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `top_level_only` | `bool` | ❌ | `false` | Rebuild only the top level of an assembly |

**Sample call:**

```json
{}
```

**Sample error response (abridged):**

```json
{
  "status": "error",
  "message": "Rebuild left 1 feature error(s): Boss-Extrude2. See data.errors for each cause and hint.",
  "data": {
    "error_count": 1,
    "errors": [
      {
        "feature": "Boss-Extrude2",
        "type": "Extrusion",
        "code": 1,
        "code_name": "swFeatureErrorUnknown",
        "severity": "error",
        "parents": [{"name": "Sketch2", "type": "ProfileFeature", "segment_count": 0}],
        "hint": "Parent sketch 'Sketch2' has no geometry. Add a closed profile to it (or delete this feature)."
      }
    ]
  }
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
