# Drawing Sheet Tools

List a drawing's sheets, add one, and choose the active one.

> **Prerequisite:** an open drawing.

**Total tools in this category: 3**

A drawing's views, dimensions, notes and tables go on its active sheet. With these tools a drawing can take several sheets: a general arrangement on one, enlarged details on another. Sheet names ignore case; an unknown name is refused with the sheets there are.

---

### `list_sheets`

List the active drawing's sheets with each one's paper size, scale and projection, and which is active.

Each sheet has `name`, `active`, `paper_mm` (`[width, height]`), `scale` (`1:2`) and `projection` (`first` or `third` angle). Sheets are read without switching between them.

**Prerequisite:** Active drawing.

**Parameters:** none.

**Sample call:**

```json
{}
```

---

### `add_sheet`

Add a sheet to the active drawing, with a format, paper size and scale, and make it the active sheet.

The format is a name such as `a3 - iso` (found in SolidWorks's sheet format folders) or a `.slddrt` path; the paper size comes from the format's name unless given. The new sheet takes the active sheet's projection unless `projection` is given. A name already used is refused.

**Prerequisite:** Active drawing.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | ✅ |  | The new sheet's name, e.g. 'Details' |
| `sheet_format` | `str` | — | `"a3 - iso"` | A sheet format by name, e.g. 'a3 - iso' or 'a2 - iso', or a .slddrt path |
| `paper_size` | `str` | — |  | Paper size; read from the format's name when omitted |
| `scale` | `str` | — | `"1:1"` | Sheet scale, e.g. '1:2' or '2:1' |
| `projection` | `str` | — |  | 'first' or 'third' angle projection; the active sheet's when omitted |

**Sample call:**

```json
{"name": "Details", "sheet_format": "a3 - iso", "scale": "2:1"}
```

---

### `activate_sheet`

Make a sheet of the active drawing the active one, so new views and notes go on it.

**Prerequisite:** Active drawing.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | ✅ |  | The sheet, as list_sheets names it |

**Sample call:**

```json
{"name": "Sheet1"}
```
