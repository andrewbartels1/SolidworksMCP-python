## ADDED Requirements

### Requirement: A coordinate system at a point
`create_coordinate_system` SHALL take `origin` (`[x, y, z]` mm) and SHALL
insert a coordinate system there with its axes along the model's. The origin is a
point in a 3D sketch the tool draws for it. The reply SHALL give the
feature's `name` and read its transform back as `origin_mm` and the three
axis directions `x_axis`, `y_axis` and `z_axis`.

#### Scenario: At a corner of a block
- **WHEN** it is called with `origin` `[20, 10, 20]` on a 40 × 40 × 10 mm
  block
- **THEN** it replies `name` "Coordinate System1", `origin_mm`
  `[20, 10, 20]` and `x_axis` `[1, 0, 0]`

#### Scenario: No turning yet
- **WHEN** a caller wants turned or reversed axes
- **THEN** the tool has no input for it: SolidWorks ignores the flip flags
  when no axis is selected (checked live), so turned axes wait for axis
  lines drawn and selected (a later change)

### Requirement: The centre-of-mass point
`create_center_of_mass_point` SHALL insert SolidWorks's Center of Mass
reference point on the active part and reply with its `name` and
`center_of_mass_mm`. A part that has one already, or has no solid body,
SHALL fail with `invalid_input` saying so.

#### Scenario: A block 10 mm tall on the Top Plane
- **WHEN** it is called on a 40 × 40 × 10 mm block
- **THEN** `center_of_mass_mm` is `[0, 5, 0]`

### Requirement: The bounding box
`create_bounding_box` SHALL insert SolidWorks's Bounding Box feature around
the part's solid bodies (best fit), optionally including hidden bodies, and
reply with its `name` and the box's `size_mm` `[x, y, z]`, read from
SolidWorks.

#### Scenario: A block
- **WHEN** it is called on a 40 × 40 × 10 mm block
- **THEN** `size_mm` holds 40, 10 and 40 (in model axes)

### Requirement: Section properties of a planar face
`get_section_properties` SHALL take `face_point` (`[x, y, z]` mm on a planar
face) and reply with the face's `area_mm2`, `centroid_mm`, the second
moments of area about the centroid in model axes (`ixx`, `iyy`, `izz`,
`ixy`, `izx`, `iyz`, mm⁴), `polar_moment_mm4` and the principal moments
`principal_moments_mm4`. It changes nothing in the model. A point on no
face, or on a face SolidWorks can't take a section of, SHALL fail with
`invalid_input`.

#### Scenario: A 40 mm square face
- **WHEN** it is given the top face of a 40 × 40 × 10 mm block
- **THEN** `area_mm2` is 1600, `centroid_mm` is `[0, 10, 0]`, and `ixx` and
  `izz` are 40⁴/12 = 213,333.3 mm⁴
