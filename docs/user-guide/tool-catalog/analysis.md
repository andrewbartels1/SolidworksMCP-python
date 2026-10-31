# Analysis Tools

Use these after a model or assembly already exists. To check a finished build in one
call, use `verify_model`. For individual readings, start with mass properties, then
interference checking, then geometry analysis, then material properties.

> **Prerequisite:** An active model or assembly with solid geometry.

**Total tools in this category: 6**

## Recommended order

1. `verify_model`: one call that checks the model against what you expected
2. `calculate_mass_properties` or `get_mass_properties`
3. `check_interference`
4. `analyze_geometry`
5. `get_material_properties`

## Known limits

- `get_mass_properties` is a compatibility alias for `calculate_mass_properties`.
- These tools do not create or modify geometry.
- In tests and local development, the mock adapter stands in for SolidWorks COM and
  returns canned success/error payloads so the suite can run without a live SolidWorks
  session, this is mostly for CI and testing use cases. Use a real SolidWorks
  installation to validate engineering results.

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

### `verify_model`

Check the active part or assembly against what you meant to build. A modelling tool
that returns success does not prove the geometry is right; this reads the model back
and compares it with your expectations. Give only the expectations you know: each one
becomes a check. With none, it just reports what it measured.

**Prerequisite:** Active part or assembly

**Parameters (all optional):**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mass_kg` | `float?` | `None` | Expected mass in kg (depends on the assigned material) |
| `volume_mm3` | `float?` | `None` | Expected volume, mm³ |
| `bounding_box_mm` | `[x, y, z]?` | `None` | Expected overall size in mm, in model axes |
| `feature_count` | `int?` | `None` | Expected modelling features; sketches, the origin, folders and the three default planes are not counted |
| `solid_body_count` | `int?` | `None` | Expected solid bodies (parts only) |
| `component_count` | `int?` | `None` | Expected top-level components (assemblies only) |
| `mate_count` | `int?` | `None` | Expected unsuppressed mates (assemblies only) |
| `no_interference` | `bool?` | `None` | `true` to require that no components overlap (assemblies only) |
| `relative_tolerance` | `float` | `0.01` | Allowed relative error for mass and volume (0.01 = 1 %) |
| `length_tolerance_mm` | `float` | `0.1` | Allowed error per bounding-box axis, mm |

Unknown parameters are rejected, so a misspelt expectation fails loudly instead of being
skipped.

**Result:** each entry in `checks` has `expected`, `actual`, `tolerance`, `unit` and
`passed`. `passed` is `true`, `false`, or `null` when the value could not be measured,
which never counts as a pass. `verdict` is one of:

- `pass`: every check passed;
- `fail`: at least one check failed;
- `inconclusive`: nothing failed, but something couldn't be measured;
- `report_only`: no expectations were given.

A model that doesn't match still returns `status: "success"`, because the tool itself
worked. `measured` holds everything that was read, including the names of the counted
features.

**Sample call:**

```json
{
  "volume_mm3": 50000,
  "bounding_box_mm": [100, 50, 10],
  "feature_count": 1,
  "solid_body_count": 1
}
```

**Tips:**

- Widen `relative_tolerance` when your hand calculation ignores fillets or chamfers.
- Widen `length_tolerance_mm` when `measured.bounding_box_method` is `assembly_box`.
  SolidWorks' assembly box can be slightly larger than the parts; part boxes are
  measured exactly from each body's extreme points.
- A failing size check whose note says "oriented differently" means the part is the
  right size but was built along different axes. Check which plane each sketch is on.
- With the mock adapter there is no geometry, so volume, size and body checks report
  `null` and the verdict is `inconclusive`.

---
