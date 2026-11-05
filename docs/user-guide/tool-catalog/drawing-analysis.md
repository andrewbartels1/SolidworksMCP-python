# Drawing Analysis Tools

Quality-gate your drawings. Analyse dimensions, annotations, view coverage, and GD&T compliance. Generate formal drawing reports and compare drawing revisions. Suitable for automated QA pipelines.

> **Prerequisite:** An active Drawing document open in SolidWorks.

**Total tools in this category: 8**

---

### `analyze_drawing_comprehensive`

Run every drawing check (dimensions, views, annotations, standards) on a drawing file in one call.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `drawing_path` | `str` | ✅ | `` | Path to drawing file (.slddrw) |
| `analysis_type` | `str` | — | `comprehensive` | Analysis type (comprehensive, dimensions, views, annotations) |
| `analysis_depth` | `str` | — | `Basic` | Analysis depth level |
| `standards_check` | `bool` | — | `True` | Check against drafting standards |
| `generate_report` | `bool` | — | `True` | Generate detailed report |

**Sample call:**

```json
{
  "drawing_path": "C:\\Temp\\mcp_demo\\file.sldprt"
}
```

---

### `analyze_drawing_dimensions`

Check a drawing's dimensions for consistent precision, tolerance formatting and completeness.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `drawing_path` | `str` | ✅ | `` | Path to drawing file |
| `check_precision` | `bool` | — | `True` | Check dimension precision consistency |
| `check_tolerances` | `bool` | — | `True` | Check tolerance formatting |
| `check_completeness` | `bool` | — | `True` | Check dimension completeness |

**Sample call:**

```json
{
  "drawing_path": "C:\\Temp\\mcp_demo\\file.sldprt"
}
```

---

### `analyze_drawing_annotations`

Check a drawing's notes, symbols and text styles for consistency.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `drawing_path` | `str` | ✅ | `` | Path to drawing file |
| `check_notes` | `bool` | — | `True` | Check note formatting and content |
| `check_symbols` | `bool` | — | `True` | Check symbol usage and placement |
| `check_text_styles` | `bool` | — | `True` | Check text style consistency |
| `check_annotations` | `bool` | — | `True` | Alias used by tests |

**Sample call:**

```json
{
  "drawing_path": "C:\\Temp\\mcp_demo\\file.sldprt"
}
```

---

### `check_drawing_compliance`

Check a drawing's title block and sheet format against a drafting standard (ISO, ANSI or DIN).

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `drawing_path` | `str` | ✅ | `` | Path to drawing file |
| `standard` | `str` | — | `ISO` | Standard to check against (ISO, ANSI, DIN) |
| `standards_to_check` | `List[str]` | ✅ | `` | Standards list alias |
| `check_title_block` | `bool` | — | `True` | Check title block compliance |
| `check_sheet_format` | `bool` | — | `True` | Check sheet format compliance |

**Sample call:**

```json
{
  "drawing_path": "C:\\Temp\\mcp_demo\\file.sldprt",
  "standards_to_check": []
}
```

---

### `analyze_drawing_views`

Check how a drawing's views are chosen and laid out.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `generate_drawing_report`

Write a quality report that combines every drawing check.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `compare_drawing_versions`

Compare two drawing files on disk: whether they are byte-identical, and how their sizes differ.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `validate_drawing_completeness`

Check that a drawing carries everything needed to manufacture the part.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---
