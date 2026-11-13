# File Management Tools

Open, save, and manage SolidWorks documents. Load parts and assemblies, save-as with new names or paths, manage custom file properties, and convert between file formats.

> **Prerequisite:** SolidWorks running. File-write operations need writable output paths.

**Total tools in this category: 19**

---

### `save_file`

Save the active document, to its own path or to a new path in its own format.

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

Save the active document under a new path, as a SolidWorks file or in an exchange format such as STEP or IGES.

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

Report the active document's file details: name, path, size, dates, type, configuration and unsaved changes.

**Prerequisite:** Active document

**Sample call:**

```json
{}
```

---

### `get_model_info`

Report the active document's title, path, type, active configuration, unsaved changes, feature count and rebuild status.

**Prerequisite:** Active document

**Sample call:**

```json
{}
```

---

### `list_features`

List the feature tree of the active part or assembly, in order.

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

Classify the active model's kind (part, sheet metal, assembly, drawing and so on) from its feature tree, and suggest how to work on it.

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

List the names of the active model's configurations.

**Prerequisite:** Active document

**Sample call:**

```json
{}
```

---

### `manage_file_properties`

Read or change the file-level properties of a SolidWorks file on disk.

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

Convert a SolidWorks file on disk to another format without opening it first.

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

Copy, move, rename or delete SolidWorks files on disk in one call.

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

Open a part (.sldprt) from disk and make it the active document.

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

Open an assembly (.sldasm) from disk and make it the active document.

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

Save the active part in place, or as a new .sldprt with the target path checked first.

**Prerequisite:** Active Part document

**Sample call:**

```json
{}
```

---

### `save_assembly`

Save the active assembly in place, or as a new .sldasm, optionally copying the parts it uses alongside.

**Prerequisite:** Active Assembly document

**Sample call:**

```json
{}
```

---

### `pack_and_go_assembly`

Copy an assembly and every file it uses into one folder that opens on its own.

SolidWorks lists the files the assembly uses (`GetDependencies2`), and each is
copied into `target_dir` under its own name. The copy opens with its own parts,
because SolidWorks looks for a referenced file in the assembly's folder before
the path stored in the assembly. The files are copied as saved on disk: save
first, or the reply's `warning` names each open file whose unsaved changes the
copy doesn't have. No document is closed or changed.

The call fails, and copies nothing, when a file the assembly uses is missing,
when two files share a name (renaming one would break the reference), or when
`target_dir` holds the originals.

(SolidWorks' own Pack and Go, `IPackAndGo`, listed only the assembly on
SolidWorks 2026, so the tool no longer uses it.)

**Prerequisite:** SolidWorks running, and the `.sldasm` on disk.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source_path` | `str` | ✅ | | The source `.sldasm` file |
| `target_dir` | `str` | ✅ | | The folder to copy into; created if needed |
| `export_preview` | `bool` | — | `False` | Write an isometric PNG preview next to the copies |
| `overwrite` | `bool` | — | `False` | Allow a folder that already has files; only the copied files are replaced |

**Sample call:**

```json
{
  "source_path": "C:\\Projects\\robot_arm.sldasm",
  "target_dir": "C:\\Exports\\robot_arm_pkg"
}
```

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | `"success"` or `"error"` |
| `method` | `str` | `"dependency_copy"` |
| `source_assembly` | `str` | The assembly packed |
| `target_dir` | `str` | The folder written |
| `copied_files` | `list[str]` | The files copied |
| `source_files` | `list[str]` | The assembly, then each file it uses |
| `unsaved_changes` | `list[str]` | Open files whose unsaved changes are not in the copy |
| `preview_image` | `str?` | The PNG preview, or `null` if it couldn't be written |
| `warning` | `str?` | Unsaved changes left out, or a preview that couldn't be written |

---

### `list_open_documents`

List every document open in SolidWorks and say which one is active.

**Prerequisite:** SolidWorks running

**Parameters:** none

**Sample call:**

```json
{}
```

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | `"success"` or `"error"` |
| `documents` | `list[dict]` | One `{title, path, type, is_active}` entry per open document |
| `count` | `int` | Number of open documents |

---

### `activate_document`

Make an already-open document the active one, so the next tools act on it.

**Prerequisite:** The target document is already open

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `title_or_path` | `str` | ✅ | `` | Window title, full path, or bare file name of an open document |

**Sample call:**

```json
{
  "title_or_path": "bracket.SLDPRT"
}
```

---

### `get_selected_entities`

Describe the faces, edges and vertices selected in the SolidWorks window right now.

**Prerequisite:** Active document with at least one entity selected in the SolidWorks UI (returns an empty list otherwise)

**Parameters:** none

**Sample call:**

```json
{}
```

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | `"success"` or `"error"` |
| `entities` | `list[dict]` | One descriptor per selected entity — `type` (`FACE`/`EDGE`/`VERTEX`) plus type-specific fields (`bounding_box_mm`/`center_mm`/`area_mm2`/`normal` for faces, `start_mm`/`end_mm`/`length_mm` for edges, `point_mm` for vertices) |
| `count` | `int` | Number of selected entities |

---

### `save_body_as_part`

Save one solid body of the active multibody part as a new part file (Insert > Features > Save Bodies).

**Prerequisite:** Active multibody part

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `body_name` | `str` | ✅ | `` | Name of a solid body in the active part, e.g. 'Boss-Extrude1' |
| `file_path` | `str` | ✅ | `` | Absolute path for the new .sldprt (parent directory must exist) |

**Sample call:**

```json
{
  "body_name": "Boss-Extrude1",
  "file_path": "C:\parts\bracket_body.sldprt"
}
```

---
