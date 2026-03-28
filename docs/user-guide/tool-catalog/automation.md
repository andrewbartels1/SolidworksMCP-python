# Automation Tools

Orchestrate multi-step workflows, run batch file processing, manage design tables, generate VBA code on the fly, and tune SolidWorks performance settings. The glue that connects individual tool calls into repeatable pipelines.

> **Prerequisite:** Varies by operation. Batch processing requires writable source/output directories.

**Total tools in this category: 8**

---

### `generate_vba_code`

Generate VBA code for SolidWorks automation.

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

### `automation_start_macro_recording`

Start recording a macro in SolidWorks.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `macro_name` | `str?` | — | `None` | Name for the recorded macro |
| `recording_name` | `str?` | — | `None` | Recording name alias |
| `output_file` | `str?` | — | `None` | Output file alias |
| `recording_mode` | `str?` | — | `None` | Recording mode alias |
| `capture_mouse` | `bool` | — | `True` | Capture mouse actions |
| `capture_keyboard` | `bool` | — | `True` | Capture keyboard actions |
| `description` | `str` | — | `` | Description of the macro functionality |
| `auto_start` | `bool` | — | `True` | Automatically start recording |

**Sample call:**

```json
{}
```

---

### `automation_stop_macro_recording`

Stop recording the current macro.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `batch_process_files`

Perform batch operations on multiple SolidWorks files.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source_directory` | `str` | ✅ | `` | Directory containing SolidWorks files |
| `operation_type` | `str?` | — | `None` | Type of operation (rebuild, save_as, export, update_properties) |
| `batch_operation` | `str?` | — | `None` | Batch operation alias |
| `target_format` | `str?` | — | `None` | Target format for export operations |
| `file_pattern` | `str?` | — | `None` | File pattern alias |
| `parallel_processing` | `bool` | — | `False` | Parallel processing alias |
| `operation` | `str?` | — | `None` | Operation alias |
| `recursive` | `bool` | — | `False` | Process subdirectories recursively |
| `filter_patterns` | `List[str]` | — | `['*.sldprt', '*.sldasm']` | File patterns to process |

**Sample call:**

```json
{
  "source_directory": "C:\\Temp\\mcp_demo"
}
```

---

### `manage_design_table`

Create or manage design tables for parametric modeling.

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

### `execute_workflow`

Execute a predefined automation workflow.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `workflow_name` | `str` | ✅ | `` | Name of the workflow |
| `steps` | `List[Dict[str, Any]]` | ✅ | `` | List of workflow steps |
| `parallel_execution` | `bool` | — | `False` | Execute compatible steps in parallel |
| `error_handling` | `str` | — | `stop` | Error handling strategy (stop, skip, retry) |

**Sample call:**

```json
{
  "workflow_name": "MCP_Demo_Part",
  "steps": []
}
```

---

### `create_template`

Create a SolidWorks template file.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `template_type` | `str` | ✅ | `` | Type of template (part, assembly, drawing) |
| `template_name` | `str` | ✅ | `` | Name for the template |
| `base_file` | `str?` | — | `None` | Base file to create template from |
| `source_model` | `str?` | — | `None` | Source model alias |
| `output_path` | `str?` | — | `None` | Output path alias |
| `include_custom_properties` | `bool` | — | `False` | Include custom properties alias |
| `include_materials` | `bool` | — | `False` | Include materials alias |
| `include_features` | `List[str]` | ✅ | `` | Include features alias |
| `metadata` | `Dict[str, Any]` | — | `{}` | Template metadata and properties |

**Sample call:**

```json
{
  "template_type": "example",
  "template_name": "MCP_Demo_Part",
  "include_features": []
}
```

---

### `optimize_performance`

Optimize SolidWorks performance settings.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---
