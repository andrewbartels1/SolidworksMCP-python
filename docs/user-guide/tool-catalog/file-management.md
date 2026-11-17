# File Management Tools

Open, save, switch and inspect SolidWorks documents: `open_model`, `save_file`,
`save_as` and `save_as_template`, the open documents, the feature tree, configurations, the current
selection and Pack and Go. `load_part`, `load_assembly`, `save_part`,
`save_assembly` and `get_file_properties` are deprecated; each section names its
replacement.

> **Prerequisite:** SolidWorks running. File-write operations need writable output paths.

**Total tools in this category: 20**

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

### `save_as_template`

Save the active part, assembly or drawing as a template, so new documents start from it.

Set a document up once (units with `set_units`, a material, custom properties), save it as a template, and pass the template to `create_part`, `create_assembly` or `create_drawing` as `template`. A part saves as `.prtdot`, an assembly as `.asmdot`, a drawing as `.drwdot`. Give `file_path`, or `name` to save in SolidWorks' first template folder (Options > File Locations > Document Templates) so it also shows in File > New. Afterwards SolidWorks has the template open in place of the document, as its own File > Save As does: `save_file` would then change the template, and the reply's `warning` says so. A document saved before is left on disk as last saved. Save from a part with no features when only its settings should carry over. A wrong extension, a missing folder, or a file already there without `overwrite` is refused (`invalid_input`) before SolidWorks is asked.

**Prerequisite:** An active document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str?` | — | `None` | The template's full path, ending in .prtdot (part), .asmdot (assembly) or .drwdot (drawing). Give this or `name` |
| `name` | `str?` | — | `None` | A name, e.g. 'Bracket MMGS': saved with the right extension in SolidWorks' first template folder, so it shows in File > New. Give this or `file_path` |
| `overwrite` | `bool` | — | `False` | Replace a template already there. Off by default. |

**Sample call:**

```json
{
  "name": "Bracket MMGS"
}
```

Then:

```json
{
  "name": "Bracket",
  "template": "C:/ProgramData/SOLIDWORKS/SOLIDWORKS 2026/templates/Bracket MMGS.prtdot"
}
```

to `create_part`.

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

> **Deprecated:** use `get_model_info`. It keeps working until 3.0.0, when it is removed.

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

List the names of the active model's configurations, and which one is active.

**Prerequisite:** Active document

**Sample call:**

```json
{}
```

---

### `create_configuration`

Add a configuration to the active part or assembly, e.g. a long and a short version of one part. The configuration that was active stays active unless `activate` is on.

**Prerequisite:** Active part or assembly.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | ✅ | `` | The new configuration's name |
| `parent` | `str?` | — | `None` | A configuration to derive it from |
| `description` | `str` | — | `""` | Its description |
| `activate` | `bool` | — | `false` | Leave it active |

**Sample call:**

```json
{"name": "Long", "parent": "Default"}
```

---

### `activate_configuration`

Make a configuration of the active model the active one, and rebuild.

**Prerequisite:** Active part or assembly with that configuration. Beta.

**Sample call:**

```json
{"name": "Long"}
```

---

### `delete_configuration`

Delete a configuration of the active model; not the active one or the only one.

**Prerequisite:** Active part or assembly with that configuration. Beta.

**Sample call:**

```json
{"name": "Long"}
```

---

### `load_part`

> **Deprecated:** use `open_model`. It keeps working until 3.0.0, when it is removed.

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

> **Deprecated:** use `open_model`. It keeps working until 3.0.0, when it is removed.

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

> **Deprecated:** use `save_file`. It keeps working until 3.0.0, when it is removed.

Save the active part in place, or as a new .sldprt with the target path checked first.

**Prerequisite:** Active Part document

**Sample call:**

```json
{}
```

---

### `save_assembly`

> **Deprecated:** use `save_file`. It keeps working until 3.0.0, when it is removed.

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
