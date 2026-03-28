# VBA Generation Tools

Generate and execute VBA macro code for operations that exceed the COM direct-call parameter limit (typically > 12 params). Covers extrusions, revolves, assembly inserts, mates, drawing views, batch exports, file operations, and macro recording scaffolding.

> **Prerequisite:** SolidWorks running. Generated VBA macros are executed via the COM runtime.

**Total tools in this category: 10**

---

### `generate_vba_extrusion`

Generate VBA code for complex extrusion operations.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sketch_name` | `str?` | — | `None` | Sketch name |
| `depth` | `float` | ✅ | `` | Extrusion depth in mm |
| `direction` | `str?` | — | `None` | Direction |
| `both_directions` | `bool` | — | `False` | Extrude in both directions |
| `depth2` | `float` | — | `0.0` | Second direction depth if both_directions=True |
| `draft_angle` | `float` | — | `0.0` | Draft angle in degrees |
| `draft_outward` | `bool` | — | `True` | Draft direction |
| `thin_feature` | `bool` | — | `False` | Create thin feature |
| `thin_thickness` | `float` | — | `1.0` | Thin feature thickness in mm |
| `thin_thickness1` | `float?` | — | `None` | Alias thickness 1 |
| `thin_thickness2` | `float?` | — | `None` | Alias thickness 2 |
| `thin_type` | `str` | — | `OneDirection` | Thin feature type |
| `cap_ends` | `bool` | — | `False` | Cap thin feature ends |
| `cap_thickness` | `float` | — | `1.0` | Cap thickness in mm |
| `merge_result` | `bool` | — | `True` | Merge with existing geometry |
| `feature_scope` | `str | bool` | — | `False` | Use feature scope |
| `auto_select` | `bool` | — | `True` | Auto select components |
| `assembly_feature_scope` | `str?` | — | `None` | Assembly feature scope |
| `start_condition` | `str?` | — | `None` | Start condition |
| `end_condition` | `str?` | — | `None` | End condition |
| `end_condition_reference` | `str?` | — | `None` | End condition reference |
| `offset_parameters` | `Dict[str, Any]?` | — | `None` | Offset parameters |
| `custom_properties` | `Dict[str, Any]?` | — | `None` | Custom properties |
| `advanced_options` | `Dict[str, Any]?` | — | `None` | Advanced options |

**Sample call:**

```json
{
  "depth": 25.0
}
```

---

### `generate_vba_revolve`

Generate VBA code for complex revolve operations.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `angle` | `float?` | — | `None` | Revolve angle in degrees |
| `angle_degrees` | `float?` | — | `None` | Angle alias |
| `sketch_name` | `str?` | — | `None` | Sketch name |
| `axis_reference` | `str?` | — | `None` | Axis reference |
| `both_directions` | `bool` | — | `False` | Revolve in both directions |
| `angle2` | `float` | — | `0.0` | Second direction angle |
| `thin_feature` | `bool` | — | `False` | Create thin feature |
| `thin_thickness` | `float` | — | `1.0` | Thin feature thickness in mm |
| `merge_result` | `bool` | — | `True` | Merge with existing geometry |

**Sample call:**

```json
{}
```

---

### `generate_vba_assembly_insert`

Generate VBA code for assembly component insertion.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `operation_type` | `str?` | — | `None` | Assembly operation (insert, mate, pattern, etc.) |
| `component_path` | `str?` | — | `None` | Path to component file |
| `assembly_file` | `str?` | — | `None` | Assembly file |
| `component_file` | `str?` | — | `None` | Component file alias |
| `insertion_point` | `List[float]` | — | `[0, 0, 0]` | Insertion coordinates [x,y,z] |
| `rotation` | `List[float]` | — | `[0, 0, 0]` | Rotation angles [rx,ry,rz] |

**Sample call:**

```json
{}
```

---

### `generate_vba_drawing_views`

Generate VBA code for drawing view creation.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `operation_type` | `str?` | — | `None` | Drawing operation (view, dimension, annotation, etc.) |
| `model_path` | `str?` | — | `None` | Path to 3D model |
| `drawing_file` | `str?` | — | `None` | Drawing file path |
| `view_layout` | `str?` | — | `None` | View layout |
| `view_scale` | `str?` | — | `None` | View scale |
| `advanced_options` | `Dict[str, Any]?` | — | `None` | Advanced options |
| `sheet_format` | `str` | — | `A3` | Sheet format (A4, A3, B, C, etc.) |
| `scale` | `float` | — | `1.0` | Drawing scale |

**Sample call:**

```json
{}
```

---

### `generate_vba_batch_export`

Generate VBA code for batch file export operations.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `operation_type` | `str?` | — | `None` | Batch operation type (export, properties, etc.) |
| `file_pattern` | `str?` | — | `None` | File pattern to process (e.g., '*.sldprt') |
| `source_folder` | `str?` | — | `None` | Source folder path |
| `target_folder` | `str?` | — | `None` | Target folder path |
| `source_directory` | `str?` | — | `None` | Source directory alias |
| `export_format` | `str?` | — | `None` | Export format alias |
| `exclude_list` | `List[str]?` | — | `None` | Exclude list |
| `recursive` | `bool` | — | `True` | Process subfolders |

**Sample call:**

```json
{}
```

---

### `generate_vba_part_modeling`

Generate VBA code for complex part modeling operations.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `generate_vba_assembly_mates`

Generate VBA code for assembly mate creation.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `generate_vba_drawing_dimensions`

Generate VBA code for creating drawing dimensions.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `generate_vba_file_operations`

Generate VBA code for file management operations.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `generate_vba_macro_recorder`

Generate VBA code using macro recording patterns.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---
