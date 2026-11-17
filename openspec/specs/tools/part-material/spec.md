# tools/part-material Specification

## Purpose
TBD - created by archiving change material-elastic-properties. Update Purpose after archive.
## Requirements
### Requirement: The assigned material's properties

`get_material` SHALL return, for the active part's material, its `material`
name, `database`, `density_kg_m3`, and `properties`: for each of elastic
modulus, Poisson's ratio, shear modulus, tensile strength, yield strength,
compressive strength, density, thermal expansion coefficient, thermal
conductivity and specific heat that the material's library entry holds, its
`value` in SI units, its `unit` and SolidWorks' `label` for it. A property
the entry doesn't hold SHALL be left out. It SHALL be read-only.

#### Scenario: AISI 1020

- **WHEN** the active part's material is AISI 1020 and `get_material` is
  called
- **THEN** `properties` holds `elastic_modulus` 2.0e11 Pa,
  `poissons_ratio` 0.29, `yield_strength` about 3.52e8 Pa and
  `tensile_strength` about 4.21e8 Pa, each with its unit

#### Scenario: A material with no yield strength

- **WHEN** the material is ABS, whose library entry has no yield strength
- **THEN** `properties` has no `yield_strength` and the other properties
  are returned

#### Scenario: No material assigned

- **WHEN** the part has no material
- **THEN** `material` is null and `properties` is empty

### Requirement: Read a library material without assigning it

Given `material` (and optionally `database`), `get_material` SHALL return
that library material's properties as above, without changing any document
and with no document open. A name no library holds SHALL be `not_found`,
naming `list_available_materials`.

#### Scenario: Compare before choosing

- **WHEN** `get_material` is called with `material: "6061-T6 (SS)"` and a
  part made of AISI 1020 is active
- **THEN** the reply gives 6061-T6's properties (elastic modulus 6.9e10 Pa)
  and the part's material is still AISI 1020

#### Scenario: An unknown material

- **WHEN** `material` is `"Unobtainium"`
- **THEN** the call fails as `not_found` and names `list_available_materials`

