# Analysis Tools

Extract engineering properties from models: mass, volume, centre of mass, moments of inertia, interference between solids, geometry curvature and thickness, and material properties. Essential for design validation.

> **Prerequisite:** An active model (part or assembly) with solid geometry.

**Total tools in this category: 5**

---

### `calculate_mass_properties`

Get mass properties of the current SolidWorks model.

**Prerequisite:** Active model with solid geometry

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `model_path` | `str?` | — | `None` | Path to the model file |
| `units` | `str` | — | `metric` | Units for mass properties |
| `include_hidden` | `bool` | — | `False` | Include hidden components |
| `reference_coordinate_system` | `str?` | — | `None` | Reference coordinate system alias |

**Sample call:**

```json
{}
```

---

### `get_mass_properties`

Backward-compatible alias for calculate_mass_properties.

**Prerequisite:** Active model with solid geometry

**Sample call:**

```json
{}
```

---

### `check_interference`

Check for interference between components in an assembly.

**Prerequisite:** Active assembly

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `assembly_path` | `str?` | — | `None` | Assembly path alias |
| `check_all_components` | `bool` | — | `False` | Check all components alias |
| `include_hidden` | `bool` | — | `False` | Include hidden components |
| `components` | `List[str]` | ✅ | `` | List of component names to check for interference |
| `tolerance` | `float` | — | `0.001` | Interference detection tolerance in mm |

**Sample call:**

```json
{
  "components": []
}
```

---

### `analyze_geometry`

Perform geometry analysis on the current model.

**Prerequisite:** Active model with geometry

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `analysis_type` | `str` | ✅ | `` | Type of analysis (curvature, draft, thickness, etc.) |
| `parameters` | `Dict[str, Any]?` | — | `None` | Analysis-specific parameters |

**Sample call:**

```json
{
  "analysis_type": "curvature"
}
```

---

### `get_material_properties`

Get material properties of the current model.

**Prerequisite:** Active part with assigned material

**Sample call:**

```json
{}
```

---
