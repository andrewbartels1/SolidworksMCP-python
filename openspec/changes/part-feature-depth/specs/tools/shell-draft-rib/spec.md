## Purpose

`create_shell`, `add_draft` and `create_rib` shape an existing body: hollow
it, taper its walls, or stiffen it, each picked by points the agent already
knows.

## ADDED Requirements

### Requirement: Shell to a wall thickness
`create_shell` SHALL take `thickness` in millimetres, `remove_face_points`
(a list of `[x, y, z]` points, each on a face to remove; may be empty for a
closed hollow body) and `outward` (default off). It SHALL make one shell
feature and reply with its name and `measured_change`.

#### Scenario: An open box
- **WHEN** a 40 × 40 × 20 mm block is active and `create_shell` is called
  with `thickness` 2 and a point on the top face
- **THEN** the volume falls to 40·40·20 − 36·36·18 = 8,672 mm³ within 0.5 %

#### Scenario: Too thick
- **WHEN** `thickness` is more than half the block's smallest size
- **THEN** the call fails, says SolidWorks could not build the shell, and
  the tree is unchanged

### Requirement: Draft faces against a neutral plane
`add_draft` SHALL take `angle` in degrees (above 0 and below 90),
`neutral_point` (a point on the neutral face) or `neutral_plane` (a plane
name), exactly one of them, and `face_points` (points on the faces to
draft, at least one). It SHALL make one draft feature and reply with its
name and `measured_change`.

#### Scenario: Drafting a block's sides
- **WHEN** a block's four side faces are drafted 5° from its bottom face
- **THEN** one draft feature appears and the volume changes

#### Scenario: Both neutral inputs
- **WHEN** `neutral_point` and `neutral_plane` are both given
- **THEN** the call fails with `invalid_input`

### Requirement: A rib from an open sketch
`create_rib` SHALL take `sketch` (the name of an open-profile sketch),
`thickness` in millimetres, `both_sides` (default on) and `flip_material`
(default off). It SHALL make one rib feature and reply with its name and
`measured_change`.

#### Scenario: A rib between two walls
- **WHEN** a sketch line runs between two walls of a shelled box and
  `create_rib` is called with `thickness` 3
- **THEN** one rib feature appears and the volume rises

#### Scenario: A rib that reaches nothing
- **WHEN** the rib's sketch does not reach the body in its material
  direction
- **THEN** the call fails and says the rib added no material
