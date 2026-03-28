# Template Management Tools

Create, extract, apply, compare, and library-manage SolidWorks document templates (.prtdot, .asmdot, .drwdot) and sheet formats. Enables standardised document creation across teams and projects.

> **Prerequisite:** Valid template file paths. Library operations require a configured template library path.

**Total tools in this category: 6**

---

### `extract_template`

Extract template from existing SolidWorks model.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source_model` | `str` | ✅ | `` | Path to source model file |
| `template_name` | `str` | ✅ | `` | Name for the extracted template |
| `template_type` | `str` | ✅ | `` | Template type (part, assembly, drawing) |
| `save_path` | `str` | ✅ | `` | Path to save the template file |
| `include_custom_properties` | `bool` | — | `True` | Include custom properties |
| `include_dimensions` | `bool` | — | `True` | Include dimensions |

**Sample call:**

```json
{
  "source_model": "example",
  "template_name": "MCP_Demo_Part",
  "template_type": "example",
  "save_path": "C:\\Temp\\mcp_demo\\file.sldprt"
}
```

---

### `apply_template`

Apply a template to an existing SolidWorks model.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `template_path` | `str` | ✅ | `` | Path to template file |
| `target_model` | `str` | ✅ | `` | Path to target model |
| `overwrite_existing` | `bool` | — | `False` | Overwrite existing properties |
| `apply_dimensions` | `bool` | — | `True` | Apply dimension formatting |
| `apply_materials` | `bool` | — | `True` | Apply material settings |

**Sample call:**

```json
{
  "template_path": "C:\\Temp\\mcp_demo\\file.sldprt",
  "target_model": "example"
}
```

---

### `batch_apply_template`

Apply template to multiple models in batch.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `template_path` | `str` | ✅ | `` | Path to template file |
| `source_folder` | `str` | ✅ | `` | Folder containing target models |
| `file_pattern` | `str` | — | `*.sldprt` | File pattern to match |
| `recursive` | `bool` | — | `True` | Process subfolders |
| `backup_originals` | `bool` | — | `True` | Create backup copies |

**Sample call:**

```json
{
  "template_path": "C:\\Temp\\mcp_demo\\file.sldprt",
  "source_folder": "example"
}
```

---

### `compare_templates`

Compare two templates and generate difference report.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `template1_path` | `str` | ✅ | `` | Path to first template |
| `template2_path` | `str` | ✅ | `` | Path to second template |
| `comparison_type` | `str` | — | `full` | Comparison type (full, properties, dimensions) |
| `comparison_depth` | `str` | — | `full` | Comparison depth alias |
| `include_properties` | `bool` | — | `True` | Include properties |
| `include_dimensions` | `bool` | — | `True` | Include dimensions |
| `include_materials` | `bool` | — | `True` | Include materials |
| `generate_report` | `bool` | — | `True` | Generate comparison report |

**Sample call:**

```json
{
  "template1_path": "C:\\Temp\\mcp_demo\\file.sldprt",
  "template2_path": "C:\\Temp\\mcp_demo\\file.sldprt"
}
```

---

### `save_to_template_library`

Save template to the organization's template library.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `list_template_library`

List available templates from the template library.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---
