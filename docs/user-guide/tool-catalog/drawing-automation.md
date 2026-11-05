# Drawing Automation Tools

Put the model's dimensions on a drawing and lay them out so nothing overlaps, add a bill of materials, set the sheet scale, or make a complete A3 drawing of a part or assembly in one call.

> **Prerequisite:** An active Drawing document with views of a model; generate_drawing_package only needs a saved part or assembly.

**Total tools in this category: 5**

---

### `insert_model_dimensions`

Bring the model's dimensions into the active drawing's views, each dimension shown once.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `arrange_dimensions`

Move drawing dimensions out of their views into tidy rows so nothing overlaps, then check the sheet.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `insert_bom_table`

Insert a bill-of-materials table for an assembly view on the active drawing.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `set_sheet_scale`

Set the active drawing sheet's scale, e.g. 1:2; views that use the sheet scale follow it.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `generate_drawing_package`

Create a complete A3 drawing of a part or assembly in one call, and save it with a PDF.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---
