## ADDED Requirements

### Requirement: Chamfers at an angle

`add_chamfer` SHALL take an `angle` in degrees (default 45) and `flip`, making an angle-distance chamfer with `distance` along one face.

#### Scenario: A 60 degree chamfer
- **WHEN** an agent chamfers a block's edge 2 mm at 60°
- **THEN** the volume removed is 0.5 x 2 x 2·tan(60°) x the edge length, within 1 %, or with the legs swapped when `flip` is set

#### Scenario: Default unchanged
- **WHEN** no angle is given
- **THEN** the chamfer is the same 45° chamfer as before
