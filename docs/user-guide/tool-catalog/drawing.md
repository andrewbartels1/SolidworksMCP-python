# Drawing Tools

Create and edit 2-D technical drawings: views, section and detail views, notes,
centre marks, dimensions by hand or automatically, the title block and sheet
format, and a check that the drawing is complete before it is exported. Every
position is in sheet millimetres from the sheet's lower-left corner.

> **Prerequisite:** An active SolidWorks Drawing (.slddrw) document.

**Total tools in this category: 13**

---

### `create_drawing_view`

Place one named view of a part or assembly on the active drawing sheet.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `model_path` | `str` | ✅ | `` | Path to the SolidWorks model file |
| `view_type` | `str` | ✅ | `` | Type of view (orthographic, isometric, section, detail) |
| `position_x` | `float` | — | `100.0` | X position in drawing (mm) |
| `position_y` | `float` | — | `200.0` | Y position in drawing (mm) |
| `scale` | `float` | — | `1.0` | View scale factor |
| `orientation` | `str` | — | `front` | View orientation (front, top, right, isometric) |

**Sample call:**

```json
{
  "model_path": null,
  "view_type": "example"
}
```

---

### `add_dimension`

Add one dimension to a drawing view, between edges picked by points on the sheet.

Points are `[x, y]` in sheet millimetres on a view's edges or vertices; read the views' outlines with `check_drawing`. Two parallel edges give their distance, one edge its length, a circle's edge its radius or diameter, two lines their angle. The reply gives the measured value. For the model's own dimensions use `insert_model_dimensions`.

**Prerequisite:** An active drawing.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `dimension_type` | `str` | ✅ | `` | `horizontal`, `vertical`, `aligned`, `radial`, `diameter` or `angular` |
| `entity1_point` | `list[float]` | ✅ | `` | `[x, y]` sheet mm on the first edge or vertex |
| `entity2_point` | `list[float]?` | — | `None` | The second entity: required for `angular`, not allowed for `radial` and `diameter` |
| `position` | `list[float]` | ✅ | `` | `[x, y]` sheet mm for the dimension text |

**Sample call:**

```json
{
  "dimension_type": "horizontal",
  "entity1_point": [40, 160],
  "entity2_point": [100, 160],
  "position": [70, 240]
}
```

---

### `add_note`

Place a text note on the active drawing sheet at a position in millimetres.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | `str` | ✅ | `` | Note text content |
| `position_x` | `float` | ✅ | `` | X position for note |
| `position_y` | `float` | ✅ | `` | Y position for note |
| `font_size` | `float` | — | `12.0` | Font size in points |
| `leader_attachment` | `str?` | — | `None` | Entity to attach leader line to |

**Sample call:**

```json
{
  "text": "example",
  "position_x": 10.0,
  "position_y": 10.0
}
```

---

### `create_section_view`

Cut a section view along a line across a drawing view, and place it on the sheet.

The line's ends are sheet millimetres and must cross the view, for example through a hole's centre. A line that misses the view, or a position off the sheet, is refused (`invalid_input`) before anything changes.

**Prerequisite:** An active drawing with the parent view.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view` | `str` | ✅ | `` | The parent view's name (`list_drawing_views`) |
| `line_start` | `list[float]` | ✅ | `` | `[x, y]` sheet mm where the section line starts |
| `line_end` | `list[float]` | ✅ | `` | `[x, y]` sheet mm where it ends |
| `position` | `list[float]` | ✅ | `` | `[x, y]` sheet mm for the new view |
| `label` | `str?` | — | `None` | The section letter; the next free one when omitted |

**Sample call:**

```json
{
  "view": "Drawing View2",
  "line_start": [20, 120],
  "line_end": [140, 120],
  "position": [500, 300]
}
```

---

### `create_detail_view`

Magnify a circular area of a drawing view as a detail view, at a scale.

The circle's centre is sheet millimetres inside the view. A centre outside the view, or a position off the sheet, is refused before anything changes.

**Prerequisite:** An active drawing with the parent view.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view` | `str` | ✅ | `` | The parent view's name |
| `center` | `list[float]` | ✅ | `` | `[x, y]` sheet mm, inside the view |
| `radius` | `float` | ✅ | `` | The detail circle's radius on the sheet, mm |
| `position` | `list[float]` | ✅ | `` | `[x, y]` sheet mm for the new view |
| `scale` | `str` | — | `2:1` | The detail's scale, e.g. `3:1` |
| `label` | `str?` | — | `None` | The detail letter; the next free one when omitted |

**Sample call:**

```json
{
  "view": "Drawing View1",
  "center": [40, 155],
  "radius": 6,
  "position": [500, 120],
  "scale": "3:1"
}
```

---

### `update_sheet_format`

Change the active drawing sheet's format and paper size, keeping every view.

Give a format name SolidWorks has (`a2 - iso`) or a `.slddrt` path. The paper size comes from the name unless given. The views are checked to be the same afterwards; the title block keeps its values, which are properties.

**Prerequisite:** An active drawing.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sheet_format` | `str` | ✅ | `` | A format name such as `a2 - iso`, or a `.slddrt` path |
| `paper_size` | `str?` | — | `None` | `a4` to `a0`; read from the format name when omitted |

**Sample call:**

```json
{
  "sheet_format": "a2 - iso"
}
```

---

### `auto_dimension_view`

Dimension one drawing view with SolidWorks' auto-dimension (baseline or chain).

It adds reference dimensions measured from the view's edges. Prefer `insert_model_dimensions`, which shows the model's own dimensions; use this for a view that has none to bring in, then `arrange_dimensions`. It fails when nothing is added.

**Prerequisite:** An active drawing with that view.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view` | `str` | ✅ | `` | The view's name |
| `scheme` | `str` | — | `baseline` | `baseline` or `chain`, both directions |

**Sample call:**

```json
{
  "view": "Section View A-A"
}
```

---

### `check_drawing`

Check the active drawing is complete before exporting it: views, dimensions, title block, BOM.

Read-only. Errors fail the drawing: `view_off_sheet` and `dangling_annotation`. Warnings don't: `view_not_dimensioned` (isometric and detail views excepted), `title_block_field_empty` (title, drawn by, revision) and `bom_missing` (an assembly with no BOM). Each finding names the tool that fixes it. It checks completeness, not a drafting standard. This tool was `check_drawing_standards`, which never worked.

**Prerequisite:** An active drawing.

**Parameters:** none.

**Returns:** `passed`, `errors`, `warnings`, `findings` (each `rule`, `severity`, `message` and maybe `view`), `views` and `report` (the facts read: sheet size, view outlines and dimension counts, title block, BOM, dangling count).

---

### `create_technical_drawing`

Place a model's three standard views (front, top and side) on the active drawing sheet in one call.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `template` | `str?` | — | `None` | Drawing template file path |
| `model_file` | `str?` | — | `None` | Model file to create drawing from |
| `sheet_size` | `str` | — | `A3` | Sheet size |
| `title` | `str` | — | `` | Drawing title |
| `output_path` | `str?` | — | `None` | Output drawing path |
| `sheet_format` | `str?` | — | `None` | Sheet format |
| `scale` | `str` | — | `1:1` | Drawing scale |
| `auto_populate_views` | `bool` | — | `False` | Automatically populate standard views |

**Sample call:**

```json
{}
```

---

### `add_drawing_view`

> **Deprecated:** use `create_drawing_view`. It keeps working until 3.0.0, when it is removed.

Place one named view of a part or assembly on the active drawing sheet; the same as `create_drawing_view`.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `drawing_path` | `str?` | — | `None` | Path to drawing file |
| `view_name` | `str?` | — | `None` | Name of the drawing view |
| `operation` | `str` | — | `add` | Operation to perform (create, update, delete) |
| `model_file` | `str?` | — | `None` | Model file path |
| `view_type` | `str?` | — | `None` | Type of view |
| `parent_view` | `str?` | — | `None` | Parent view alias |
| `position` | `List[float]?` | — | `None` | View position |
| `scale` | `str?` | — | `None` | View scale |
| `parameters` | `Dict[str, Any]` | — | `{}` | View parameters |

**Sample call:**

```json
{}
```

---

### `update_title_block`

Change the active drawing's title-block fields: title, drawing number, drawn by, date, revision, company.

Each field is written to the property the sheet format shows, the same mapping `generate_drawing_package` uses: the title is the drawn model's `Description`, the others are the drawing's own properties (`DrawingNo`, `DrawnBy`, `DrawnDate`, `Revision`, `COMPANYNAME`). Fields not given keep their values. The ISO format's DWG NO. box shows the file name, not `DrawingNo`.

**Prerequisite:** An active drawing of a model.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `title` | `str?` | — | `None` | The title (the model's Description) |
| `drawing_number` | `str?` | — | `None` | The drawing number |
| `drawn_by` | `str?` | — | `None` | Drawn by |
| `drawn_date` | `str?` | — | `None` | Date drawn |
| `revision` | `str?` | — | `None` | Revision, e.g. `B` |
| `company` | `str?` | — | `None` | Company name |

At least one is required.

**Sample call:**

```json
{
  "revision": "B"
}
```

---

### `auto_center_marks`

Insert centre marks on the holes, slots and (optionally) fillets of one drawing view.

**Prerequisite:** Active drawing containing the named view

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view_name` | `str` | ✅ | `` | Name of a view on the active drawing, e.g. 'Drawing View1' |
| `mark_holes` | `bool` | — | `true` | Mark holes / bores |
| `mark_fillets` | `bool` | — | `false` | Mark fillets |
| `mark_slots` | `bool` | — | `true` | Mark slots |

**Sample call:**

```json
{
  "view_name": "Drawing View1"
}
```

---

### `list_drawing_views`

List the views on the active drawing, by name.

**Prerequisite:** Active drawing

**Parameters:** none

**Sample call:**

```json
{}
```

**Sample response:**

```json
{
  "status": "success",
  "message": "3 view(s): Drawing View1, Drawing View2, Drawing View3",
  "views": ["Drawing View1", "Drawing View2", "Drawing View3"],
  "count": 3
}
```

---
