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

**Which way a cut goes.** A one-way `create_cut_extrude` (`Blind` or `ThroughAll`)
goes along the sketch plane's normal. From a sketch on a face, or on a plane that
touches the body on one side only (a Top Plane sketch under a block extruded up from
it), that direction can point away from the material. The tool then cuts the other way
and its reply has `cut_extrude.direction_flipped: true`, so there's no need to guess
`reverse_direction`. For a sketch on a plane through the middle of a body, use
`ThroughAllBoth` (or `ThroughAll` with `both_directions: true`) to cut both sides. If
neither direction removes material, the error is `feature_not_built`: change the
sketch, its plane or the depth rather than retrying the same call.

---

### `open_model`

Open a part, assembly or drawing from disk and make it the active document.

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

Create a new, empty part document and make it active, ready for `create_sketch`.

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

Create a new, empty assembly document and make it active, ready for `insert_component`.

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

Create a new, empty drawing document and make it active.

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

Close the active document, saving it first only if asked.

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

Extrude the sketch you just closed into a solid boss, added to the active part.

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

Revolve the sketch you just closed around the centreline drawn in it, adding a solid to the active part.

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

Read one dimension of the active model by its full name, e.g. "D1@Sketch1".

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

Change one length dimension of the active model, in mm, and rebuild.

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

Set the active document's length units: mm, cm, m, in or ft.

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

Rename a feature in the active model's feature tree.

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

Select a feature, sketch, plane or component by name in the active document.

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

Select every edge of one face of the active part, ready for `add_fillet` or `add_chamfer` with no edge names.

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

Rebuild the active model and report each feature that fails, with the reason and a fix.

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

Add a reference point on an edge (at a distance or percentage along it) or at the centre of a face.

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
