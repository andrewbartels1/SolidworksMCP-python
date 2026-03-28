# Drawing Tools

Create and edit 2-D technical drawings: add projected/section/detail views, place dimensions, notes, and annotations, update title blocks and sheet formats, and run drafting standards checks.

> **Prerequisite:** An active SolidWorks Drawing (.slddrw) document.

**Total tools in this category: 12**

---

### `create_drawing_view`

Create a drawing view of a SolidWorks model.

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

Add a dimension to the current drawing.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `dimension_type` | `str` | ✅ | `` | Type of dimension (linear, radial, angular, diameter) |
| `entity1` | `str` | ✅ | `` | First entity to dimension (edge, face, point) |
| `entity2` | `str?` | — | `None` | Second entity for linear/angular dimensions |
| `position_x` | `float` | ✅ | `` | X position for dimension text |
| `position_y` | `float` | ✅ | `` | Y position for dimension text |
| `precision` | `int` | — | `2` | Number of decimal places |

**Sample call:**

```json
{
  "dimension_type": "linear",
  "entity1": "Line1",
  "position_x": 10.0,
  "position_y": 10.0
}
```

---

### `add_note`

Add a note or annotation to the current drawing.

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

Create a section view of the current drawing.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `section_line_start` | `List[float]` | ✅ | `` | Start point of section line as [x, y] |
| `section_line_end` | `List[float]` | ✅ | `` | End point of section line as [x, y] |
| `view_position_x` | `float` | ✅ | `` | X position for section view |
| `view_position_y` | `float` | ✅ | `` | Y position for section view |
| `scale` | `float` | — | `1.0` | Section view scale |
| `label` | `str` | — | `A` | Section view label |

**Sample call:**

```json
{
  "section_line_start": [],
  "section_line_end": [],
  "view_position_x": 10.0,
  "view_position_y": 10.0
}
```

---

### `create_detail_view`

Create a detail view of a specific area.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `center_x` | `float` | ✅ | `` | X center of detail circle |
| `center_y` | `float` | ✅ | `` | Y center of detail circle |
| `radius` | `float` | ✅ | `` | Radius of detail circle |
| `view_position_x` | `float` | ✅ | `` | X position for detail view |
| `view_position_y` | `float` | ✅ | `` | Y position for detail view |
| `scale` | `float` | — | `2.0` | Detail view scale |
| `label` | `str` | — | `A` | Detail view label |

**Sample call:**

```json
{
  "center_x": 0.0,
  "center_y": 0.0,
  "radius": 15.0,
  "view_position_x": 10.0,
  "view_position_y": 10.0
}
```

---

### `update_sheet_format`

Update the sheet format and title block information.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `format_file` | `str` | ✅ | `` | Path to sheet format template (.slddrt) |
| `sheet_size` | `str` | — | `A3` | Sheet size (A4, A3, A2, A1, A0) |
| `title` | `str` | — | `` | Drawing title |
| `drawn_by` | `str` | — | `` | Drawn by field |
| `checked_by` | `str` | — | `` | Checked by field |
| `approved_by` | `str` | — | `` | Approved by field |
| `drawing_number` | `str` | — | `` | Drawing number |

**Sample call:**

```json
{
  "format_file": "example"
}
```

---

### `auto_dimension_view`

Automatically dimension a drawing view.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `check_drawing_standards`

Check the current drawing against drafting standards.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `create_technical_drawing`

Create a technical drawing from a SolidWorks part or assembly.

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

Add, update, or remove a drawing view in an existing drawing.

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

### `add_annotation`

Add an annotation such as a note, balloon, or surface symbol.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `drawing_path` | `str?` | — | `None` | Path to drawing file |
| `annotation_type` | `str` | ✅ | `` | Type of annotation (note, balloon, surface_finish, etc.) |
| `text` | `str` | ✅ | `` | Annotation text content |
| `position_x` | `float?` | — | `None` | X position for annotation |
| `position_y` | `float?` | — | `None` | Y position for annotation |
| `position` | `List[float]?` | — | `None` | Annotation position |
| `font_size` | `float` | — | `12.0` | Font size in points |
| `leader_attachment` | `str?` | — | `None` | Entity to attach leader line to |
| `drawn_by` | `str` | — | `` | Drawn by field |
| `checked_by` | `str` | — | `` | Checked by field |
| `approved_by` | `str` | — | `` | Approved by field |
| `drawing_number` | `str` | — | `` | Drawing number |

**Sample call:**

```json
{
  "annotation_type": "example",
  "text": "example"
}
```

---

### `update_title_block`

Update title block fields for the active drawing.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---
