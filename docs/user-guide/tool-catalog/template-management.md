# Template Management Tools

Compare two SolidWorks template files (.prtdot, .asmdot, .drwdot) on disk. To
start a part from a template, give `template` to `create_part`.

> **Prerequisite:** Both template files on disk.

**Total tools in this category: 1**

---

### `compare_templates`

Compare two template files on disk: whether they are byte-identical, and how their sizes differ.

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

