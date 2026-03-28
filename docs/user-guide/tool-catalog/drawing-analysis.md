# Drawing Analysis Tools

Quality-gate your drawings. Analyse dimensions, annotations, view coverage, and GD&T compliance. Generate formal drawing reports and compare drawing revisions. Suitable for automated QA pipelines.

> **Prerequisite:** An active Drawing document open in SolidWorks.

**Total tools in this category: 8**

---

### `analyze_drawing_comprehensive`

Perform comprehensive analysis of SolidWorks drawing.

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

Analyze dimensions in a SolidWorks drawing for consistency and completeness.

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

Analyze drawing annotations and notes quality.

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

Check drawing compliance with company standards.

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

Analyze drawing views arrangement and quality.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `generate_drawing_report`

Generate comprehensive drawing analysis report.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `compare_drawing_versions`

Compare different versions of drawing files.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `validate_drawing_completeness`

Validate drawing completeness for production readiness.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---
