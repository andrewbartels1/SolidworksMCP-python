## ADDED Requirements

### Requirement: Sweeps that add or remove material
`create_sweep` SHALL sweep a closed profile along a path and add material;
`create_cut_sweep` SHALL do the same and remove material. The path is a
sketch or a curve such as a helix, named by `path`. The profile is, in
order of preference: a circle of `circular_profile_diameter` mm (no profile
sketch), the sketch named by `profile`, or the sketch closed last that
isn't the path. Both take `twist_along_path` and `twist_angle` (degrees);
`create_sweep` keeps `merge_result`.

#### Scenario: A named profile
- **WHEN** `create_sweep` is called with `path` and `profile` naming two
  sketches
- **THEN** that profile is swept along that path, whatever sketch was
  closed last

#### Scenario: A circle with no profile sketch
- **WHEN** `create_sweep` is called with a helix as `path` and
  `circular_profile_diameter` 2
- **THEN** a 2 mm wire is swept along the helix, and the reply says the
  profile was a 2 mm circle

#### Scenario: A cut sweep removes material
- **WHEN** `create_cut_sweep` sweeps a closed profile that overlaps a solid
  along a helix
- **THEN** the part's volume goes down, and the reply gives the volume
  before, after and the change

#### Scenario: The profile is unclear
- **WHEN** neither `profile` nor `circular_profile_diameter` is given and
  no sketch other than the path exists, or `profile` names the path itself
- **THEN** the call fails as `invalid_input`, naming the sketches found

### Requirement: A sweep is judged by the volume
Both sweeps SHALL report the part's volume before and after and the change
in mm³. A sweep that changes nothing, or changes it the wrong way (a cut
that adds), SHALL be removed again and reported as an error, so a failed
sweep never stays in the tree.

#### Scenario: A cut that misses the part
- **WHEN** `create_cut_sweep` sweeps a profile that doesn't touch the solid
- **THEN** the call fails saying the volume didn't change, and the feature
  is not left in the tree
