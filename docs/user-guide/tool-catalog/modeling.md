# Modeling Tools

Create and manipulate SolidWorks parts, assemblies, and drawings. These are the foundational tools for any CAD workflow — opening files, creating features (extrude, revolve), and querying/setting driven dimensions.

> **Prerequisite:** An active SolidWorks session. Most feature tools require an open Part document.

**Total tools in this category: 42**

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

It changes the active configuration only, unless `configurations` is `"all"` or a list of names; the reply's `configurations` names where it was set. An unknown name is refused (`invalid_input`) before anything changes.

**Prerequisite:** Active document with named dimensions

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str?` | — | `None` | Dimension name (e.g., 'D1@Sketch1', 'D1@Boss-Extrude1') |
| `dimension_name` | `str?` | — | `None` | Dimension name alias |
| `value` | `float` | ✅ | `` | New dimension value in millimeters |
| `units` | `str?` | — | `None` | Units alias |
| `configurations` | `str \| list[str]` | — | `this` | `this` (the active configuration), `all`, or names from `list_configurations` |

**Sample call:**

```json
{
  "name": "D1@Boss-Extrude1",
  "value": 50.0,
  "configurations": ["Long"]
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

### `create_hole`

Add a standard Hole Wizard hole (simple, counterbored, countersunk or tapped) at a point on a flat face.

Every point in `positions` adds another hole to the same feature, as placing holes on sketch points does in the Hole Wizard. Sizes are checked against SolidWorks' Hole Wizard library first (see [`list_hole_sizes`](#list_hole_sizes)): a size that isn't there is refused with the nearest ones, and nothing is made. On a simple hole a screw size (`M6`, `#10`) makes a clearance hole and a bare diameter (`6`) a drilled one; the reply's `fastener` names the hole type used. SolidWorks makes no simple hole through all, so a simple `through_all` hole is made blind through the part; the reply's `end_condition_used` says `blind` and a warning explains.

**Prerequisite:** Active part with a flat face at `face_point`.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `face_point` | `list[float]` | ✅ | `` | `[x, y, z]` in mm on a flat face: the hole's centre |
| `hole_type` | `str` | ✅ | `` | `simple`, `counterbore`, `countersink` or `tapped` |
| `standard` | `str` | — | `iso` | `iso`, `ansi_inch`, `ansi_metric`, `din` or `jis` |
| `size` | `str` | ✅ | `` | As `list_hole_sizes` lists it: `M6`, `#10`, `1/4`; `M6x1.0` finds the coarse M6 thread |
| `fastener` | `str?` | — | `None` | A hole type's name from `list_hole_sizes` (e.g. `Dowel Holes`); the usual one when omitted |
| `end_condition` | `str` | — | `through_all` | `through_all` or `blind` |
| `depth` | `float?` | — | `None` | Blind depth in mm (required for `blind`) |
| `positions` | `list[list[float]]?` | — | `None` | More holes in the same feature: `[x, y, z]` mm points on the same face |

**Sample call:**

```json
{
  "face_point": [10, 10, 20],
  "hole_type": "counterbore",
  "size": "M6",
  "positions": [[30, 10, 20], [10, 30, 20]]
}
```

---

### `list_hole_sizes`

List the Hole Wizard's hole types and sizes for a standard, or one size's dimensions.

Read from SolidWorks' installed Hole Wizard library (the Toolbox file `swbrowser.sldedb`, found through the registry or the `SOLIDWORKS_MCP_HOLE_LIBRARY` setting), read-only, so it works without SolidWorks running. With `size`, it gives that size's dimensions as the library stores them: counterbore diameter and depth, head diameter, pitch, in mm (inches for `ansi_inch`).

**Prerequisite:** SolidWorks' Toolbox library on this machine.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `hole_type` | `str` | ✅ | `` | `simple`, `counterbore`, `countersink` or `tapped` |
| `standard` | `str` | — | `iso` | `iso`, `ansi_inch`, `ansi_metric`, `din` or `jis` |
| `fastener` | `str?` | — | `None` | One hole type's name (e.g. `Screw Clearances`): only its sizes |
| `size` | `str?` | — | `None` | One size (e.g. `M6`): its dimensions |

**Sample call:**

```json
{
  "hole_type": "counterbore",
  "fastener": "Cap (4762)",
  "size": "M6"
}
```

---

### `add_cosmetic_thread`

Add a cosmetic thread to a hole or shaft, so drawings show the thread callout.

**Prerequisite:** Active part with a round edge at `edge_point`.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `edge_point` | `list[float]` | ✅ | `` | `[x, y, z]` in mm on the circular edge where the thread starts |
| `size` | `str` | ✅ | `` | Thread size, e.g. `M10x1.5` or `1/4-20` |
| `diameter` | `float?` | — | from a metric size | Major diameter in mm |
| `end_type` | `str` | — | `blind` | `blind`, `up_to_next` or `through` |
| `depth` | `float?` | — | `None` | Blind length in mm (required for `blind`) |
| `standard` | `str` | — | `iso` | `iso` or `ansi_inch` |

**Sample call:**

```json
{
  "edge_point": [5, 0, 30],
  "size": "M10x1.5",
  "depth": 15
}
```

---

### `pattern_linear`

Repeat features of the active part in a row or a grid, e.g. a row of holes.

**Prerequisite:** Active part with the named features.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `features` | `list[str]` | ✅ | `` | Names of the features to repeat |
| `direction` | `list[float]` or `str` | ✅ | `` | `[x, y, z]` mm on a straight edge, or an axis name |
| `count` | `int` | ✅ | `` | Instances along it, the original included (2+) |
| `spacing` | `float` | ✅ | `` | Distance between instances, mm |
| `direction2` | `list[float]` or `str` | — | `None` | Second direction, for a grid |
| `count2` | `int` | — | `1` | Instances along the second direction |
| `spacing2` | `float` | — | `0` | Spacing along the second direction, mm |
| `reverse`, `reverse2` | `bool` | — | `false` | Flip a direction |

**Sample call:**

```json
{
  "features": ["CBORE for M6 Socket Head Cap Screw1"],
  "direction": [0, -20, 20],
  "count": 3,
  "spacing": 12
}
```

---

### `create_shell`

Hollow the active part to a wall thickness, opening the faces picked.

**Prerequisite:** Active part with a solid body.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `thickness` | `float` | ✅ | `` | Wall thickness, mm |
| `faces` | `list[list[float]]` | — | `[]` | `[x, y, z]` mm on each face to remove |
| `outward` | `bool` | — | `false` | Put the wall outside the body |

**Sample call:**

```json
{"thickness": 2, "faces": [[0, 0, 20]]}
```

---

### `add_draft`

Draft faces of the active part by an angle, e.g. for a moulded part.

**Prerequisite:** Active part.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `angle` | `float` | ✅ | `` | Draft angle in degrees (under 90) |
| `faces` | `list[list[float]]` | ✅ | `` | `[x, y, z]` mm on each face to draft |
| `neutral_face` | `list[float]` | ✅ | `` | `[x, y, z]` mm on the face the draft pivots on |
| `reverse` | `bool` | — | `false` | Draft the other way |

**Sample call:**

```json
{
  "angle": 3,
  "faces": [[20, 0, 10], [-20, 0, 10]],
  "neutral_face": [0, 0, 0]
}
```

---

### `create_base_flange`

Start a sheet-metal part: a base flange from a sketch, with its thickness, bend radius and K-factor.

A closed sketch (a rectangle) makes a flat plate; an open one (a line or an L) makes a bent profile extruded by `depth`. The thickness, radius and K-factor are read back from the feature.

**Prerequisite:** Active part with the profile sketch closed.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `thickness` | `float` | ✅ | `` | Sheet thickness, mm |
| `bend_radius` | `float` | ✅ | `` | Inside bend radius, mm |
| `k_factor` | `float` | — | `0.5` | The bend allowance's K-factor |
| `depth` | `float?` | — | `None` | How far an open profile is extruded, mm; required for one |
| `sketch` | `str?` | — | `None` | The profile's sketch; the last closed one when omitted |
| `reverse` | `bool` | — | `false` | Thicken to the other side of the sketch |

**Sample call:**

```json
{"thickness": 2, "bend_radius": 2}
```

---

### `add_edge_flange`

Add a flange to one edge of a sheet-metal part, at a length and angle.

Pick the edge with a point on it in mm. `length` is measured from that edge: on a 2 mm sheet a 20 mm flange stands 22 mm above the bottom face. The reply's `edge_length_mm` shows which edge was picked.

**Prerequisite:** A sheet-metal part (`create_base_flange` first).

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `edge_point` | `list[float]` | ✅ | `` | `[x, y, z]` mm on the sheet's edge |
| `length` | `float` | ✅ | `` | The flange's length from the edge, mm |
| `angle` | `float` | — | `90` | The flange's angle, degrees |
| `bend_radius` | `float?` | — | `None` | Inside bend radius, mm; the sheet's when omitted |
| `flip` | `bool` | — | `false` | Put the flange on the other side |

**Sample call:**

```json
{"edge_point": [0, 0, 30], "length": 20}
```

---

### `create_sketched_bend`

Bend a sheet-metal part along a line sketched on one of its faces.

Sketch a line across a face (`create_sketch` with `face_point`, then `add_line`), close the sketch, then call this. SolidWorks chooses which side of the line stays put; the reply's `bounding_box_mm` shows which side moved, and `reverse` bends the other way.

**Prerequisite:** A sheet-metal part and the bend-line sketch, closed.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `angle` | `float` | — | `90` | The bend angle, degrees |
| `bend_radius` | `float?` | — | `None` | Inside bend radius, mm; the sheet's when omitted |
| `sketch` | `str?` | — | `None` | The bend line's sketch; the last closed one when omitted |
| `reverse` | `bool` | — | `false` | Bend the other way |

**Sample call:**

```json
{"angle": 90}
```

---

### `set_flat_pattern`

Flatten a sheet-metal part to its blank, or fold it back, and measure it.

Flattened, `bounding_box_mm` is the blank to cut: a 100 x 60 x 2 mm plate with a 20 mm flange (2 mm radius, K 0.5) flattens to 100 x 78.71 mm. Then `export_flat_pattern` writes the DXF. Fold it back before adding more features.

**Prerequisite:** A sheet-metal part.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `flat` | `bool` | — | `true` | `true` flattens, `false` folds back |

**Sample call:**

```json
{"flat": true}
```

---

### `create_rib`

Add a rib from a sketched line, stiffening a wall or the inside of a shell.

**Prerequisite:** Active part and a closed rib sketch holding an open line.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sketch` | `str` | ✅ | `` | The rib sketch's name |
| `thickness` | `float` | ✅ | `` | Rib thickness, mm |
| `both_sides` | `bool` | — | `true` | Thicken both sides of the sketch |
| `flip_material` | `bool` | — | `false` | Extend the rib the other way |
| `normal_to_sketch` | `bool` | — | `false` | Extrude normal to the sketch instead of parallel |

**Sample call:**

```json
{"sketch": "Sketch3", "thickness": 2}
```

---
