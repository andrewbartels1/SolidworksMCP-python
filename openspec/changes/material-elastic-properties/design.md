## Context

`get_material` (real adapter, `adapters/solidworks/documentation.py`) reads
the name and library with `IPartDoc.GetMaterialPropertyName2`, then the
density from the material's entry in its `.sldmat` library
(`_material_density`), found through `_material_folders`. The libraries
installed with SolidWorks 2026 hold each material's properties as elements
in SI units, each with a `displayname`:

| Element | Property | Unit | Materials with it (of 259, `solidworks materials.sldmat`) |
| --- | --- | --- | --- |
| `EX` | Elastic modulus | Pa | 220 |
| `NUXY` | Poisson's ratio | (none) | 201 |
| `GXY` | Shear modulus | Pa | 184 |
| `SIGXT` | Tensile strength | Pa | 219 |
| `SIGYLD` | Yield strength | Pa | 167 |
| `SIGXC` | Compressive strength | Pa | 31 |
| `DENS` | Density | kg/m³ | 259 |
| `ALPX` | Thermal expansion coefficient | 1/K | 178 |
| `KX` | Thermal conductivity | W/(m·K) | 215 |
| `C` | Specific heat | J/(kg·K) | 184 |

AISI 1020: `EX` 0.20E+12, `NUXY` 0.29, `SIGYLD` 3.51571E+8, `SIGXT`
4.20507E+8. ABS has no `SIGYLD`.

## Goals / Non-Goals

**Goals:** the properties an agent sizes a part with, with units, from the
same file SolidWorks reads; a library material's properties without
assigning it.

**Non-Goals:** stress-strain curves, hardening factors and material models
(`materialcurve`, `RK`); writing or editing materials; unit conversion (the
reply is SI, and says so).

## Decisions

### 1. Read the library file, not COM

The properties come from the `.sldmat` entry, as density already does.
`IPartDoc.GetMaterialPropertyValues` returns only colour and optical
values, and no COM call outside Simulation returns a part material's
modulus or strengths. A library material can't be edited inside a part
(a changed material is saved to a custom library), so the library entry is
what the part uses.

*Alternative:* Simulation's material API. Rejected: it needs the Simulation
add-in and licence.

### 2. One reader for all properties

`_material_density` becomes `_material_entry(files, name, database)`,
returning every known property of the entry (the table above), with the
same library-first search order. Density is read from it. Parsing stays
with `defusedxml`.

### 3. Keys and shape

`properties` maps a snake_case key (`elastic_modulus`, `poissons_ratio`,
`shear_modulus`, `tensile_strength`, `yield_strength`,
`compressive_strength`, `density`, `thermal_expansion`,
`thermal_conductivity`, `specific_heat`) to `{value, unit, label}`. The label
is the library's `displayname`. Values are SI floats, as stored; the
description tells agents to divide Pa by 1e6 for MPa.

### 4. A library material by name

`get_material(material=..., database=None)` skips the part: no document
type guard and no COM call other than reading the library folders. When no
library holds the name, a `LookupError` names `list_available_materials`,
which the classifier maps to `not_found`. The reply's `source` is `library`,
or `part` for the assigned material.

## Risks / Trade-offs

- [A custom library stores other units] → the `.sldmat` format stores SI
  (SolidWorks converts on display); the live test reads the installed
  library.
- [The same name in two libraries] → the given `database`, or the part's
  own, is searched first, as for density.
