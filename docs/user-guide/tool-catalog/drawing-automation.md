# Drawing Automation Tools

Put the model's dimensions on a drawing and lay them out so nothing overlaps, add a bill of materials, set the sheet scale, or make a complete A3 drawing of a part or assembly in one call.

> **Prerequisite:** An active Drawing document with views of a model; generate_drawing_package only needs a saved part or assembly.

**Total tools in this category: 7**

---

### `insert_model_dimensions`

Bring the model's dimensions into the active drawing's views, each dimension shown once.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view_name` | `str?` | — | `null` | One view, e.g. 'Drawing View1'; every orthographic view when omitted. Find names with list_drawing_views. |
| `include_hole_wizard` | `bool` | — | `true` | Also import Hole Wizard location dimensions |

**Sample call:**

```json
{}
```

---

### `arrange_dimensions`

Move drawing dimensions out of their views into tidy rows so nothing overlaps, then check the sheet.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view_name` | `str?` | — | `null` | Only move this view's dimensions, e.g. 'Drawing View1'; every view when omitted. The overlap check always covers the whole sheet. |

**Sample call:**

```json
{}
```

---

### `insert_bom_table`

Insert a bill-of-materials table for an assembly view on the active drawing.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view_name` | `str` | ✅ |  | A view of an assembly, e.g. 'Drawing View1' |
| `template_path` | `str?` | — | `null` | .sldbomtbt template; bom-standard when omitted |
| `bom_type` | `str` | — | `"top_level_only"` | BOM structure |
| `x_mm` | `float?` | — | `null` | Table X on the sheet (mm); the sheet's BOM anchor when omitted |
| `y_mm` | `float?` | — | `null` | Table Y on the sheet (mm) |

**Sample call:**

```json
{"view_name": "Drawing View1"}
```

---

### `set_sheet_scale`

Set the active drawing sheet's scale, e.g. 1:2; views that use the sheet scale follow it.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `numerator` | `float` | ✅ |  | e.g. 1 for 1:2 |
| `denominator` | `float` | ✅ |  | e.g. 2 for 1:2 |

**Sample call:**

```json
{"numerator": 1, "denominator": 2}
```

---

### `generate_drawing_package`

Create a complete A3 drawing of a part or assembly in one call, and save it with a PDF.

Every title-block field the sheet format fills from a property (DWG NO., TITLE, material, drawn by and the rest) is shrunk until it fits its box; the reply's `title_block` lists each one with `fits` and its text height before and after.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `model_path` | `str` | ✅ |  | Full path to the .SLDPRT or .SLDASM |
| `output_dir` | `str?` | — | `null` | Where to save the drawing; the model's folder when omitted |
| `title` | `str?` | — | `null` | Short title, e.g. 'Mounting Plate - Rev A'; the file name when omitted |
| `subtitle` | `str?` | — | `null` | Sheet title, e.g. 'Base support' |
| `drawing_number` | `str?` | — | `null` | DWG NO., also the drawing file name, e.g. 'MP-RevA-01' |
| `author` | `str` | — | `""` | DRAWN name |
| `revision` | `str` | — | `"A"` | Revision letter |
| `company` | `str` | — | `""` | Company name |
| `notes` | `list[str]` | — | `[]` | Extra note lines (material, process, connections); 3-7 lines in total |
| `include_isometric` | `bool` | — | `true` | Add an isometric view |
| `write_model_properties` | `bool` | — | `true` | Write Description/Material/Weight into the model so the title block shows them, and save it |
| `title_block_text_height_mm` | `float?` | — | `null` | Largest text height (mm) for the title block's fields (DWG NO., TITLE and every other field the format fills from a property), e.g. 3 for smaller text. By default they keep the sheet format's height and are only shrunk to fit their boxes. |
| `include_bom` | `bool` | — | `false` | Assemblies only: put a bill of materials in the top of the isometric view's cell, with the isometric fitted below it |

**Sample call:**

```json
{"model_path": "C:\\Temp\\mcp_demo\\part.SLDPRT"}
```

---

---

### `add_gtol`

Add a GD&T feature control frame to the active drawing, e.g. position Ø0.2 (M) to A|B|C.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `characteristic` | `str` | ✅ |  | Geometric characteristic |
| `tolerance` | `float` | ✅ |  | Tolerance value, e.g. 0.2 |
| `diameter_zone` | `bool` | — | `false` | Cylindrical zone: Ø before the tolerance |
| `material_condition` | `str` | — | `"none"` | Material condition modifier |
| `datums` | `list[str]` | — | `[]` | Datum letters, primary first |
| `x_mm` | `float` | — | `0.0` | Frame X on the sheet (mm); not used when on a dimension |
| `y_mm` | `float` | — | `0.0` | Frame Y on the sheet (mm); not used when on a dimension |
| `attach_x_mm` | `float?` | — | `null` | X of a point on the edge the leader points to |
| `attach_y_mm` | `float?` | — | `null` | Y of a point on the edge the leader points to |
| `dimension_view` | `str?` | — | `null` | View holding the dimension to attach to |
| `dimension_name` | `str?` | — | `null` | Model dimension to attach to, e.g. 'D3@Sketch1' (see list_model_dimensions); the frame sits under its text |

**Sample call:**

```json
{"characteristic": "position", "tolerance": 0.2, "diameter_zone": true, "datums": ["A", "B"], "dimension_view": "Drawing View1", "dimension_name": "D3@Sketch1"}
```

---

### `add_datum_tag`

Add a datum feature symbol (A, B, C, ...) on an edge of the active drawing.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `label` | `str` | ✅ |  | Datum letter, e.g. 'A' |
| `attach_x_mm` | `float` | ✅ |  | X of a point on the edge it marks (mm) |
| `attach_y_mm` | `float` | ✅ |  | Y of a point on the edge it marks (mm) |
| `x_mm` | `float` | ✅ |  | Tag X on the sheet (mm) |
| `y_mm` | `float` | ✅ |  | Tag Y on the sheet (mm) |

**Sample call:**

```json
{"label": "A", "attach_x_mm": 60, "attach_y_mm": 120, "x_mm": 60, "y_mm": 135}
```
