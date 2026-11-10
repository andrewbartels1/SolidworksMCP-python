# tools/mass-properties Specification

## Purpose
The units and values `calculate_mass_properties` and `get_mass_properties`
report, so every number matches the unit printed beside it.
## Requirements
### Requirement: Moments of inertia in kg·mm²

`calculate_mass_properties` SHALL report the moments and products of inertia
in kg·mm², labelled `kg·mm²`, matching the millimetres used for the centre of
mass.

#### Scenario: A steel block
- **WHEN** an agent measures a 100 × 50 × 20 mm block of material with density 7,800 kg/m³ (mass 0.78 kg), about its centre of mass
- **THEN** `Ixx`, `Iyy` and `Izz` match m·(b² + c²)/12 for each axis in kg·mm² within 0.1 %, for example m·(50² + 20²)/12 = 188.5 kg·mm² about the 100 mm axis

