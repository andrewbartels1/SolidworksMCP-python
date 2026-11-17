## 1. Reading the library

- [x] 1.1 `_material_entry` in `adapters/solidworks/documentation.py`: every property in design decision 3 from a material's `.sldmat` entry, the given library first; `density_kg_m3` read through it
- [x] 1.2 Tests against small `.sldmat` fixtures written in the test (UTF-16 like the installed files, a missing property, a bad value, a name in two libraries)

## 2. Adapter

- [x] 2.1 `get_material(configuration, material, database)` on the base adapter, circuit breaker and connection pool, with tests
- [x] 2.2 The real adapter: `properties` and `source` for the assigned material; a library material by name with no document; `not_found` for an unknown name; tests
- [x] 2.3 The mock adapter: its materials' properties, a library read by name; tests

## 3. Tool

- [x] 3.1 `GetMaterialInput` gains `material` and `database`; the description lists the properties and SI units; tests

## 4. Docs

- [x] 4.1 The engineering-data catalog entry, the skill's workflows (read the modulus before sizing), CHANGELOG

## 5. Live check

- [x] 5.1 (passed 2026-11-16, first run; density x volume matched the mass SolidWorks measured, 0.2528 kg) `tests/live/test_live_sw_material_properties.py`: AISI 1020 assigned and its properties read; 6061-T6 and ABS read by name without assigning them (ABS with no yield); an unknown name refused
- [x] 5.2 Sign-off, archive, the queue updated
