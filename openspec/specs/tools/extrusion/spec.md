# tools/extrusion Specification

## Purpose
TBD - created by archiving change ujoint-tool-gaps. Update Purpose after archive.
## Requirements
### Requirement: The reply says what was extruded

`create_extrusion` SHALL report the end condition SolidWorks applied and, for a thin wall, its thickness and side, and SHALL NOT echo inputs it didn't apply.

#### Scenario: Both directions
- **WHEN** an agent extrudes with `both_directions: true`
- **THEN** the body is symmetric about the sketch plane and the reply's `end_condition` is `MidPlane`

### Requirement: Thin extrudes from an open profile

`create_extrusion` with `thin_feature` SHALL extrude an open sketch into a wall of `thin_thickness`, on the side `thin_side` names.

#### Scenario: A bent plate
- **WHEN** an agent extrudes an open L-shaped chain 38.1 mm with a 6.35 mm thin wall
- **THEN** one solid body is made whose volume is the chain's length times 6.35 times 38.1 mm, within 1 %

