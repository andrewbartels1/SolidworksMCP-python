# Export Tools

Convert SolidWorks models to industry-standard interchange and manufacturing formats: STEP, IGES, STL, PDF, DWG, and raster images. Includes a batch-export tool for processing whole directories.

> **Prerequisite:** An active document or a valid file path to an existing model.

**Total tools in this category: 7**

---

### `export_step`

Export the current model to STEP format.

**Prerequisite:** Active or specified model document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str` | ✅ | `` | Full path for the exported file |
| `format_type` | `str` | ✅ | `` | Export format (step, iges, stl, pdf, dwg, jpg, png) |
| `options` | `Dict[str, Any]?` | — | `None` | Format-specific export options |

**Sample call:**

```json
{
  "file_path": "C:\\Temp\\mcp_demo\\part.sldprt",
  "format_type": "step"
}
```

---

### `export_iges`

Export the current model to IGES format.

**Prerequisite:** Active or specified model document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str` | ✅ | `` | Full path for the exported file |
| `format_type` | `str` | ✅ | `` | Export format (step, iges, stl, pdf, dwg, jpg, png) |
| `options` | `Dict[str, Any]?` | — | `None` | Format-specific export options |

**Sample call:**

```json
{
  "file_path": "C:\\Temp\\mcp_demo\\part.sldprt",
  "format_type": "step"
}
```

---

### `export_stl`

Export the current model to STL format.

**Prerequisite:** Active or specified model document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str` | ✅ | `` | Full path for the exported file |
| `format_type` | `str` | ✅ | `` | Export format (step, iges, stl, pdf, dwg, jpg, png) |
| `options` | `Dict[str, Any]?` | — | `None` | Format-specific export options |

**Sample call:**

```json
{
  "file_path": "C:\\Temp\\mcp_demo\\part.sldprt",
  "format_type": "step"
}
```

---

### `export_pdf`

Export the current model or drawing to PDF format.

**Prerequisite:** Active or specified drawing document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str` | ✅ | `` | Full path for the exported file |
| `format_type` | `str` | ✅ | `` | Export format (step, iges, stl, pdf, dwg, jpg, png) |
| `options` | `Dict[str, Any]?` | — | `None` | Format-specific export options |

**Sample call:**

```json
{
  "file_path": "C:\\Temp\\mcp_demo\\part.sldprt",
  "format_type": "step"
}
```

---

### `export_dwg`

Export the current drawing to DWG format.

**Prerequisite:** Active or specified drawing document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str` | ✅ | `` | Full path for the exported file |
| `format_type` | `str` | ✅ | `` | Export format (step, iges, stl, pdf, dwg, jpg, png) |
| `options` | `Dict[str, Any]?` | — | `None` | Format-specific export options |

**Sample call:**

```json
{
  "file_path": "C:\\Temp\\mcp_demo\\part.sldprt",
  "format_type": "step"
}
```

---

### `export_image`

Export images of the current model.

**Prerequisite:** Active document

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str?` | — | `None` | Full path for the exported image |
| `output_path` | `str?` | — | `None` | Alternative output path |
| `model_path` | `str?` | — | `None` | Path to the model file |
| `format_type` | `str` | — | `jpg` | Image format (jpg, png, bmp, tiff) |
| `format` | `str?` | — | `None` | Alternative format field |
| `image_format` | `str?` | — | `None` | Image format alias |
| `width` | `int` | — | `1920` | Image width in pixels |
| `height` | `int` | — | `1080` | Image height in pixels |
| `resolution` | `str?` | — | `None` | Resolution alias |
| `view_orientation` | `str` | — | `isometric` | View orientation (front, top, right, isometric, current) |
| `orientation` | `str?` | — | `None` | Alternative orientation field |

**Sample call:**

```json
{}
```

---

### `batch_export`

Batch export multiple SolidWorks files to a target format.

**Prerequisite:** Writable source and output directories

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source_directory` | `str` | ✅ | `` | Directory containing SolidWorks files |
| `output_directory` | `str` | ✅ | `` | Directory for exported files |
| `format_type` | `str?` | — | `None` | Target export format |
| `export_format` | `str?` | — | `None` | Alternative export format |
| `file_pattern` | `str?` | — | `None` | File pattern alias |
| `recursive` | `bool` | — | `False` | Search subdirectories recursively |
| `include_subdirectories` | `bool` | — | `False` | Include subdirectories in search |
| `file_patterns` | `List[str]` | — | `['*.sldprt', '*.sldasm', '*.slddrw']` | File patterns to include |

**Sample call:**

```json
{
  "source_directory": "C:\\Temp\\mcp_demo",
  "output_directory": "C:\\Temp\\mcp_demo\\exports"
}
```

---
