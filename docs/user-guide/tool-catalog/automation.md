# Automation Tools

`generate_vba_code` writes a VBA macro skeleton for a step the other tools don't
cover. `manage_design_table` is planned: whether it is built depends on a live check
of SolidWorks' design tables (it needs Excel).

> **Prerequisite:** None for `generate_vba_code`; it only writes text.

**Total tools in this category: 2**

## Known limits

- `generate_vba_code` writes macro text; it does not run it. Run a saved `.swp`
  with `execute_macro`.
- Mock mode returns the same text as real mode, since nothing calls SolidWorks.

---

### `generate_vba_code`

Write a VBA macro skeleton for an operation you describe: the SolidWorks connection, the active document and optional error handling, with the operation itself left as a TODO.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `operation_description` | `str?` | — | `None` | Description of the operation to generate VBA for |
| `operation_type` | `str?` | — | `None` | Operation type alias |
| `parameters` | `Dict[str, Any]` | ✅ | `` | Operation parameters |
| `target_document` | `str` | — | `Part` | Target document type (Part, Assembly, Drawing) |
| `include_error_handling` | `bool` | — | `True` | Include error handling in generated code |
| `code_style` | `str` | — | `professional` | Code style (simple, professional, advanced) |

**Sample call:**

```json
{
  "parameters": {}
}
```

---

### `manage_design_table`

Create, read or update a design table (an Excel sheet that drives a model's configurations).

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `table_type` | `str?` | — | `None` | Type of design table (create, update, import) |
| `model_path` | `str?` | — | `None` | Model path alias |
| `table_file` | `str?` | — | `None` | Design table file alias |
| `operation` | `str?` | — | `None` | Operation alias |
| `auto_update` | `bool` | — | `False` | Auto update alias |
| `create_configurations` | `bool` | — | `False` | Create configurations alias |
| `auto_create_configurations` | `bool` | — | `False` | Auto-create alias |
| `excel_file` | `str?` | — | `None` | Excel file path for import/export |
| `parameters` | `List[str]` | — | `[]` | Parameters to include in design table |
| `configurations` | `List[str]` | — | `[]` | Configuration names |

**Sample call:**

```json
{}
```

---

