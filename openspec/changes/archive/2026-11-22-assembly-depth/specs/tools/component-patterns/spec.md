## ADDED Requirements

### Requirement: Repeat components in a row or around an axis
`pattern_components` SHALL take the seed `components`, an `axis` (a
reference axis's name, e.g. from `create_axis`), `count` (2 or more,
including the seeds) and either `spacing` (mm, `kind` `linear`, the
default) or `angle` (degrees, `kind` `circular`; 360 spaces them equally).
It SHALL add a component pattern feature and reply with its name and the
component count before and after.

#### Scenario: Four pins in a row
- **WHEN** one pin is patterned along the x axis, `count` 4, `spacing` 25
- **THEN** the assembly holds three more pins, 25 mm apart

#### Scenario: A count of one
- **WHEN** `count` is 1
- **THEN** it fails as `invalid_input` and nothing is added

### Requirement: Mirror components about a plane
`mirror_components` SHALL take `components` and a `plane` (`Front Plane`,
`Top Plane`, `Right Plane` or a plane's name), add mirrored instances of the
same parts on the other side of the plane, and reply with the new
instances' names.

#### Scenario: A foot mirrored to the other end
- **WHEN** a foot at x = 50 mm is mirrored about the Right Plane
- **THEN** a second foot stands at x = -50 mm, an instance of the same part

#### Scenario: A plane that isn't there
- **WHEN** `plane` names a plane the assembly doesn't have
- **THEN** it fails as `not_found` and nothing is added
