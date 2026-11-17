# tools/sheet-metal Specification

## Purpose
TBD - created by archiving change sheet-metal. Update Purpose after archive.
## Requirements
### Requirement: A base flange from a sketch

`create_base_flange` SHALL make a sheet-metal base flange from the last
closed sketch of the active part: a closed profile gives a flat plate of
`thickness`; an open profile gives a bent profile extruded by `depth`
(required then), with bends of `bend_radius`. The bend allowance SHALL be
the given `k_factor` (default 0.5). The reply SHALL give the feature's
name and the thickness, bend radius and K-factor read back from it, and
the volume.

#### Scenario: A plate

- **WHEN** a 100 x 60 mm rectangle is sketched on the Top Plane and
  `create_base_flange` is called with `thickness: 2`
- **THEN** the part is sheet metal, its volume is 12,000 mm³, and the reply
  gives thickness 2, the bend radius and K-factor 0.5

#### Scenario: An open profile with no depth

- **WHEN** the sketch is an open L and `depth` is not given
- **THEN** the call is `invalid_input` and nothing is built

### Requirement: An edge flange

`add_edge_flange` SHALL add a flange of `length` (measured from the picked
edge) at `angle` (default 90°) to the sheet-metal edge nearest `edge_point`
(mm), with the sheet's bend
radius unless `bend_radius` is given. A part that isn't sheet metal, or a
point with no sheet edge near it, SHALL be refused with nothing built. The
reply SHALL give the feature's name and the volume added.

#### Scenario: A flange on the plate's long edge

- **WHEN** a 20 mm flange is added to a 100 mm edge of the 2 mm plate
- **THEN** the volume grows by about 100 x 20 x 2 mm³ plus the bend's

### Requirement: A sketched bend

`create_sketched_bend` SHALL bend the sheet along the line of the last
closed sketch, drawn on one of its faces, by `angle` (`reverse` bends the
other way). SolidWorks chooses which side stays put; the reply SHALL give
the bounding box after, so the agent sees which side moved.

#### Scenario: Bending a plate in two

- **WHEN** a line across the middle of the plate's top face is sketched and
  `create_sketched_bend` is called with `angle: 90`
- **THEN** a bend is added and the part's bounding box is no longer flat

### Requirement: The flat pattern

`set_flat_pattern` SHALL flatten the active sheet-metal part (`flat:
true`) or fold it back (`flat: false`), and the reply SHALL give the
part's bounding box in that state: flattened, the blank's size.

#### Scenario: The blank of the flanged plate

- **WHEN** the plate with its 20 mm flange is flattened
- **THEN** the bounding box's width is 60 + (20 + 2) − 3.288 = 78.712 mm
  (the bend deduction from K = 0.5 and a 2 mm radius), within 0.1 mm, and
  folding it back restores the folded size

#### Scenario: Not sheet metal

- **WHEN** the active part is an extruded block
- **THEN** each of `add_edge_flange`, `create_sketched_bend` and
  `set_flat_pattern` is refused and says to start with
  `create_base_flange`

