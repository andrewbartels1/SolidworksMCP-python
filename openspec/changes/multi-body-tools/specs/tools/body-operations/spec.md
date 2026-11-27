## ADDED Requirements

### Requirement: Bodies are named as list_bodies names them
Every body operation SHALL take bodies by the names `list_bodies` gives,
ignoring case. A name that matches no solid body SHALL fail with
`invalid_input` before anything changes. The message SHALL name the unknown
body and list the bodies that exist.

#### Scenario: A misspelt body
- **WHEN** `combine_bodies` names a tool body `Boss-Extrude9` that doesn't
  exist
- **THEN** the call fails with `invalid_input`, the message lists the
  part's bodies, and the feature tree is unchanged

### Requirement: Every operation is measured
On success, every body operation SHALL reply with the new feature's `name`,
`bodies_before` and `bodies_after` (the names), `body_count_before`,
`body_count_after`, `volume_before_mm3`, `volume_after_mm3` and
`volume_change_mm3`. When the result breaks the rule for its operation (in
the requirements below), the call SHALL fail with `feature_not_built`, the
new feature SHALL be deleted, and the message SHALL give the counts and
volumes it found. Volumes count as unchanged within 0.1%.

#### Scenario: A subtract that removes nothing
- **WHEN** `combine_bodies` subtracts a tool body that doesn't touch the
  main body, and SolidWorks still makes a feature
- **THEN** the call fails with `feature_not_built`, the combine feature is
  deleted, and both bodies are back as they were

### Requirement: Combine bodies
`combine_bodies` SHALL take `operation` (`add`, `subtract` or `common`),
`main_body` and `tool_bodies` (one or more names, none of them the main
body). `add` SHALL leave fewer bodies and no more volume than before.
`subtract` and `common` SHALL leave less volume than before. The tool bodies
are consumed.

#### Scenario: A block minus a cylinder
- **WHEN** a 40 × 40 × 10 mm block has a 10 mm diameter cylinder through
  it as a separate body, and `combine_bodies` subtracts the cylinder from
  the block
- **THEN** one body remains, its volume is
  `16000 - pi * 5^2 * 10` mm³, and the reply names the combine feature

#### Scenario: The main body among the tools
- **WHEN** `tool_bodies` includes `main_body`
- **THEN** the call fails with `invalid_input` and nothing changes

### Requirement: Split a body
`split_body` SHALL take `tool`, the name of a plane or a sketch that crosses
the part's bodies, and optionally `bodies`, the ones to split (all by
default). The result SHALL have more bodies than before and the same
volume. The reply SHALL name the bodies made.

#### Scenario: A block split at its middle
- **WHEN** a 40 × 40 × 10 mm block centred on the origin is split by the
  Right Plane
- **THEN** there are two bodies of 8000 mm³ each, and the volume is
  unchanged

#### Scenario: A plane that misses the body
- **WHEN** the tool is a plane that doesn't cross any named body
- **THEN** the call fails, and no split feature remains

### Requirement: Move or copy bodies
`move_copy_body` SHALL take `bodies`, a `translate` `[x, y, z]` in mm, and
optionally a `rotate` `[x, y, z]` in degrees about `rotation_point`
`[x, y, z]` mm (the origin by default). With `copy: true` and `copies` N
(1 by default, at most 50), the bodies SHALL be copied N times instead of
moved.

- A move SHALL keep the body count and the volume, and SHALL change the
  moved bodies' bounding boxes.
- A copy SHALL add N bodies per body copied, and N times their volume.
- A call with no translation and no rotation SHALL fail with
  `invalid_input`.

#### Scenario: A block moved 50 mm along x
- **WHEN** a block is moved by `[50, 0, 0]`
- **THEN** its bounding box moves 50 mm along x, and the count and volume
  are unchanged

#### Scenario: Three copies
- **WHEN** a 1000 mm³ body is copied with `copies` 3 and `translate`
  `[20, 0, 0]`
- **THEN** there are 3 more bodies and 3000 mm³ more volume

### Requirement: Delete or keep bodies
`delete_bodies` SHALL take `bodies` and `keep` (false by default). With
`keep` false the named bodies SHALL be removed. With `keep` true every
other body SHALL be removed. In both cases the volume SHALL fall by the
removed bodies' volumes. Removing every body SHALL fail with
`invalid_input` before anything changes.

#### Scenario: Keep one of three
- **WHEN** a part has three bodies and `delete_bodies` keeps one
- **THEN** one body remains, with its own volume

### Requirement: Scale bodies
`scale_body` SHALL take `scale` (one factor, uniform) or `scale_xyz`
`[x, y, z]`, all above 0, `about` (`centroid`, the default, or `origin`),
and optionally `bodies` (all by default). The volume of the scaled bodies
SHALL be multiplied by the product of the factors, within 0.5%. A factor of
exactly 1 on every axis SHALL fail with `invalid_input`.

#### Scenario: A block scaled by 2
- **WHEN** a 16000 mm³ block is scaled by 2 about its centroid
- **THEN** its volume is 128000 mm³, and its centroid stays where it was

### Requirement: Mock adapter
The mock adapter SHALL keep a list of bodies with volumes and boxes, made
by unmerged extrusions. It SHALL apply each operation to that list by the
rules above, and SHALL refuse what the real adapter refuses, with the same
messages.

#### Scenario: Subtract on the mock
- **WHEN** the mock part has two bodies and one is subtracted from the
  other
- **THEN** one body remains, and the reply carries the counts and volumes
  before and after
