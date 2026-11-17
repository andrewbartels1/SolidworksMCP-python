## Why

An agent sizing a part needs the material's stiffness and strength, but
`get_material` reads only its name, library and density; the rest means
opening the material in SolidWorks. Queue item 20, found by item 10's
ledger: `get_material_properties` was removed and nothing replaced it.

## What Changes

- `get_material` also returns the material's mechanical and thermal
  properties, each with its value, SI unit and SolidWorks' own name: elastic
  modulus, Poisson's ratio, shear modulus, tensile, yield and compressive
  strength, density, thermal expansion, conductivity and specific heat. A
  property the library doesn't hold for that material is left out, never
  guessed.
- `get_material` takes an optional `material` (and `database`) to read any
  library material without assigning it, so an agent can compare materials
  before choosing one. That works with no document open.
- `density_kg_m3` stays in the reply, unchanged.

## Capabilities

### New Capabilities
- `tools/part-material`: reading a part's material, or a library material,
  with its properties and units.

### Modified Capabilities
None.

## Impact

- `adapters/solidworks/documentation.py`: `_material_density` becomes a
  reader of all the properties from the material's `.sldmat` entry (plain
  file reads, no new COM calls); `get_material` gains `material` and
  `database`.
- Base adapter interface, circuit breaker, connection pool and mock adapter:
  `get_material`'s new optional arguments. No new COM-threading risk: the
  only COM calls are the existing ones.
- `tools/engineering_data.py`: `GetMaterialInput` and the description.
- No issue filed; queue item 20.
