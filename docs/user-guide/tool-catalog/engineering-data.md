# Engineering Data Tools

Read and edit the data drawings, BOMs and analyses are built from: every model dimension by name, measurements between faces, edges and vertices, materials, custom properties, and sheet-metal flat patterns.

> **Prerequisite:** An active Part (or Assembly, for dimensions and measuring) document.

**Total tools in this category: 8**

---

### `list_model_dimensions`

List every dimension in the active part or assembly with its full name.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `measure_entities`

Measure faces, edges or vertices with SolidWorks' Measure tool.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `entities` | `List[str]` | ✅ | `` | One or two entities to measure. Each is 'face:x,y,z' (a point inside the face), 'edge:x,y,z', 'vertex:x,y,z', a bare 'x,y,z' (nearest edge) or a topology name like 'Edge<1>'. Coordinates are in metres. One face gives area/perimeter; one edge gives length/radius; two entities give distance and angle. |

**Sample call:**

```json
{
  "entities": []
}
```

---

### `get_material`

Read the material assigned to the active part.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `set_material`

Assign a library material to the active part.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `material_name` | `str` | ✅ | `` | Exact library name, e.g. 'AISI 1020', '6061-T6 (SS)', 'ABS'. Use list_available_materials to find it. |
| `database` | `str?` | — | `None` | Library; 'SOLIDWORKS Materials' when omitted |
| `configuration` | `str?` | — | `None` | Configuration; all configurations when omitted |

**Sample call:**

```json
{
  "material_name": "MCP_Demo_Part"
}
```

---

### `list_available_materials`

List materials in the installed SolidWorks material libraries.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `get_custom_properties`

Read the active document's custom properties.

**Prerequisite:** SolidWorks running

**Sample call:**

```json
{}
```

---

### `set_custom_property`

Create or overwrite one text custom property on the active document.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | ✅ | `` | Property name, e.g. 'PartNo', 'Description', 'DrawnBy' |
| `value` | `str` | ✅ | `` | Text value; may be a $PRP:"SW-Mass" style link |
| `configuration` | `str?` | — | `None` | Configuration; file-level when omitted |

**Sample call:**

```json
{
  "name": "MCP_Demo_Part",
  "value": 50.0
}
```

---

### `export_flat_pattern`

Export the active sheet-metal part's flat pattern to DXF or DWG.

**Prerequisite:** SolidWorks running

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | `str` | ✅ | `` | Output path ending in .dxf or .dwg |

**Sample call:**

```json
{
  "file_path": "C:\\Temp\\mcp_demo\\part.sldprt"
}
```

---
