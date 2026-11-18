# Analysis Tools

Use these after a model or assembly already exists. To check a finished build in one
call, use `verify_model`. For individual readings, use `get_mass_properties` and
`check_interference`.

> **Prerequisite:** An active model or assembly with solid geometry.

**Total tools in this category: 4**

## Recommended order

1. `verify_model`: one call that checks the model against what you expected
2. `get_mass_properties`
3. `check_interference`

## Known limits

- `calculate_mass_properties` is deprecated: it returns what `get_mass_properties` returns.
- These tools do not create or modify geometry.
- In tests and local development, the mock adapter stands in for SolidWorks COM and
  returns canned success/error payloads so the suite can run without a live SolidWorks
  session, this is mostly for CI and testing use cases. Use a real SolidWorks
  installation to validate engineering results.

---

### `calculate_mass_properties`

> **Deprecated:** use `get_mass_properties`. It keeps working until 3.0.0, when it is removed.

Measure the active part or assembly's mass properties: volume, surface area, mass, centre of mass and moments of inertia.

**Prerequisite:** Active model with solid geometry

**Parameters:** none. It always measures the active model; the inputs it used to take are refused.

**Sample call:**

```json
{}
```

---

### `get_mass_properties`

Measure the active part or assembly's mass properties: volume, surface area, mass, centre of mass and moments of inertia.

**Prerequisite:** Active model with solid geometry

**Sample call:**

```json
{}
```

---

### `check_interference`

Find where the components of the active assembly overlap (Tools > Interference Detection).

**Prerequisite:** Active assembly

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `assembly_path` | `str?` | — | `null` | Assembly path alias |
| `include_hidden` | `bool` | — | `false` | Check hidden components too; by default they are left out, as in SolidWorks' own Interference Detection |
| `components` | `list[str]` | — | `[]` | List of component names to check for interference |

**Sample call:**

```json
{
  "components": []
}
```

---

### `verify_model`

Check the active part or assembly against what you meant to build, one pass/fail check per expected value.
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

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `mass_kg` | `float?` | — | `null` | Expected mass in kg (depends on the material) |
| `volume_mm3` | `float?` | — | `null` | Expected volume, mm³ |
| `bounding_box_mm` | `list[float]?` | — | `null` | Expected overall size [x, y, z] in mm, in model axes |
| `feature_count` | `int?` | — | `null` | Expected number of modelling features (extrudes, cuts, fillets, patterns...); sketches, the origin, folders and the three default planes are not counted |
| `solid_body_count` | `int?` | — | `null` | Expected number of solid bodies (parts) |
| `component_count` | `int?` | — | `null` | Expected top-level components (assemblies) |
| `mate_count` | `int?` | — | `null` | Expected unsuppressed mates (assemblies) |
| `no_interference` | `bool?` | — | `null` | true to require that no components overlap (assemblies) |
| `relative_tolerance` | `float` | — | `0.01` | Allowed relative error for mass and volume (0.01 = 1 %) |
| `length_tolerance_mm` | `float` | — | `0.1` | Allowed error per bounding-box axis, mm |

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
