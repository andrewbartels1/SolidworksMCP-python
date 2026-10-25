# Drawing Automation Tools

Finish drawings: put the model's dimensions on the views and lay them out so nothing overlaps, add a bill of materials, set the sheet scale, or make a complete A3 drawing with a filled title block and a PDF in one call.

> **Prerequisite:** An active Drawing document with views of a model; generate_drawing_package only needs the model file.

**Total tools in this category: 5**

---

### `insert_model_dimensions`

Bring the model's dimensions into the active drawing's views.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `arrange_dimensions`

Move drawing dimensions so nothing overlaps, then check the real result.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `insert_bom_table`

Insert a bill-of-materials table for a view of an assembly.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view_name` | `str` | ✅ | `` | A view of an assembly, e.g. 'Drawing View1'. Find names with list_drawing_views. |
| `template_path` | `str?` | — | `None` | .sldbomtbt template; bom-standard.sldbomtbt from the BOM templates folder when omitted |
| `bom_type` | `Literal['top_level_only', 'parts_only', 'indented']` | — | `top_level_only` | top_level_only: the assembly's own components; parts_only: every part, sub-assemblies flattened; indented: the tree, numbered by level |
| `x_mm` | `float?` | — | `None` | Table X on the sheet (mm); the sheet format's BOM anchor unless x_mm and y_mm are both given |
| `y_mm` | `float?` | — | `None` | Table Y on the sheet (mm) |

**Sample call:**

```json
{
  "view_name": "Drawing View1"
}
```

---

### `set_sheet_scale`

Set the active drawing sheet's scale, e.g. 1:2.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `numerator` | `float` | ✅ | `` | e.g. 1 for 1:2 |
| `denominator` | `float` | ✅ | `` | e.g. 2 for 1:2 |

**Sample call:**

```json
{
  "numerator": 1,
  "denominator": 2
}
```

---

### `generate_drawing_package`

Create a complete A3 drawing of a part or assembly, saved with a PDF.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `model_path` | `str` | ✅ | `` | Full path to the .SLDPRT or .SLDASM |
| `output_dir` | `str?` | — | `None` | Where to save the drawing and PDF; the model's folder when omitted |
| `title` | `str?` | — | `None` | Short title, e.g. 'Mounting Plate'; the file name when omitted |
| `subtitle` | `str?` | — | `None` | Shown in the company field when company is empty, e.g. 'Base support' |
| `drawing_number` | `str?` | — | `None` | DWG NO., also the drawing file name, e.g. 'MP-RevA-01'; <MODEL>-Rev<revision>-01 when omitted |
| `author` | `str` | — | `` | DRAWN name |
| `revision` | `str` | — | `A` | Revision letter |
| `company` | `str` | — | `` | Company name |
| `notes` | `List[str]` | — | `[]` | Extra note lines after the standard ones (material, units, projection, deburr); seven lines are shown at most |
| `include_isometric` | `bool` | — | `True` | Add an isometric view |
| `write_model_properties` | `bool` | — | `True` | Write Description/Material/Weight into the model so the title block shows them, and save the model |
| `title_block_text_height_mm` | `float?` | — | `None` | Largest text height (mm) for the title block's DWG NO. and TITLE, e.g. 3 for smaller text. By default they keep the sheet format's height and are only shrunk to fit their boxes. |

**Sample call:**

```json
{
  "model_path": null
}
```

---
