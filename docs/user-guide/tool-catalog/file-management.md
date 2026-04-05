# File Management Tools

Open, save, and manage SolidWorks documents. Load parts and assemblies, save-as with new names or paths, manage custom file properties, and convert between file formats.

> **Prerequisite:** SolidWorks running. File-write operations need writable output paths.

**Total tools in this category: 13**

---

### `save_file`

Save the current SolidWorks model.

**Prerequisite:** Active open document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `force_save` | `bool` | — | `True` | Force save even if no changes |
| `file_path` | `str?` | — | `None` | Optional output path. If omitted, saves the current active document. |

**Sample call:**

```json
{}
```

---

### `save_as`

Save the current model to a new location or format.

**Prerequisite:** Active open document, writable output path

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str` | ✅ | `` | Full path for the new file |
| `format_type` | `str` | — | `solidworks` | File format (solidworks, step, iges, etc.) |
| `overwrite` | `bool` | — | `False` | Overwrite existing file |

**Sample call:**

```json
{
  "file_path": "C:\\Temp\\mcp_demo\\part.sldprt"
}
```

---

### `get_file_properties`

Get properties of the current SolidWorks file.

**Prerequisite:** Active document

**Sample call:**

```json
{}
```

---

### `get_model_info`

Get compact metadata for the active SolidWorks document.

**Prerequisite:** Active document

**Sample call:**

```json
{}
```

---

### `list_features`

List feature-tree entries for the active SolidWorks document.

**Prerequisite:** Active document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `include_suppressed` | `bool` | — | `False` | Include suppressed features in the returned list |

**Sample call:**

```json
{}
```

---

### `classify_feature_tree`

Classify the active model into a likely feature family using `get_model_info` and `list_features`.

Useful for routing between direct MCP modeling, VBA-backed workflows, assembly planning,
and low-confidence “inspect more” cases before any write operations.

**Prerequisite:** Active document, unless you pass `model_info` and `features` explicitly

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `include_suppressed` | `bool` | — | `True` | Include suppressed features when reading the active model tree |
| `model_info` | `Dict[str, Any]?` | — | `None` | Optional pre-fetched model-info payload |
| `features` | `List[Dict[str, Any]]?` | — | `None` | Optional pre-fetched feature-tree payload |

**Sample call:**

```json
{}
```

---

### `list_configurations`

List configuration names for the active SolidWorks document.

**Prerequisite:** Active document

**Sample call:**

```json
{}
```

---

### `manage_file_properties`

Read, update, copy, move, rename, or delete file-related properties.

**Prerequisite:** Active document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `operation` | `str` | ✅ | `` | Operation to perform (copy, move, delete, rename) |
| `source_path` | `str?` | — | `None` | Source file path |
| `file_path` | `str?` | — | `None` | Alternative file path |
| `target_path` | `str?` | — | `None` | Target file path (for copy/move/rename) |
| `properties` | `Dict[str, Any]?` | — | `None` | File properties to set |
| `parameters` | `Dict[str, Any]?` | — | `None` | Operation parameters |
| `include_system` | `bool` | — | `False` | Include system properties |

**Sample call:**

```json
{
  "operation": "example"
}
```

---

### `convert_file_format`

Convert a SolidWorks file from one format to another.

**Prerequisite:** Valid source file path

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source_file` | `str` | ✅ | `` | Source file path |
| `target_file` | `str?` | — | `None` | Target file path |
| `source_format` | `str?` | — | `None` | Source file format |
| `target_format` | `str` | ✅ | `` | Target file format |
| `output_path` | `str?` | — | `None` | Alternative output path |
| `conversion_options` | `Dict[str, Any]?` | — | `None` | Conversion options |
| `quality` | `str` | — | `high` | Conversion quality |
| `units` | `str` | — | `mm` | Units |
| `invalid_format` | `str?` | — | `None` | Invalid format for testing |

**Sample call:**

```json
{
  "source_file": "example",
  "target_format": "example"
}
```

---

### `batch_file_operations`

Run a file operation across multiple files as a batch workflow.

**Prerequisite:** Writable directories

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `operation` | `str` | ✅ | `` | Operation to perform (copy, move, delete, rename) |
| `source_path` | `str?` | — | `None` | Source file path |
| `file_path` | `str?` | — | `None` | Alternative file path |
| `target_path` | `str?` | — | `None` | Target file path (for copy/move/rename) |
| `properties` | `Dict[str, Any]?` | — | `None` | File properties to set |
| `parameters` | `Dict[str, Any]?` | — | `None` | Operation parameters |
| `include_system` | `bool` | — | `False` | Include system properties |

**Sample call:**

```json
{
  "operation": "example"
}
```

---

### `load_part`

Load (open) a SolidWorks part file.

**Prerequisite:** SolidWorks running, valid .sldprt path

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str` | ✅ | `` | Full path to the .sldprt file |

**Sample call:**

```json
{
  "file_path": "C:\\Temp\\mcp_demo\\part.sldprt"
}
```

---

### `load_assembly`

Load (open) a SolidWorks assembly file.

**Prerequisite:** SolidWorks running, valid .sldasm path

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str` | ✅ | `` | Full path to the .sldasm file |

**Sample call:**

```json
{
  "file_path": "C:\\Temp\\mcp_demo\\part.sldprt"
}
```

---

### `save_part`

Save the active SolidWorks part document.

**Prerequisite:** Active Part document

**Sample call:**

```json
{}
```

---

### `save_assembly`

Save the active SolidWorks assembly document.

**Prerequisite:** Active Assembly document

**Sample call:**

```json
{}
```

---
