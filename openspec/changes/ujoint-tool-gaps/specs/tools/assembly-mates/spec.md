## ADDED Requirements

### Requirement: Mate a face by a point on it

`add_mate` SHALL accept, for each side, either a named entity or a point on a face in that component's own part coordinates (mm), and SHALL pick the face among that component's faces only.

#### Scenario: A pin concentric in a hole
- **WHEN** an agent mates a pin's cylindrical face (a point on it) concentric with a bracket's hole face (a point on it)
- **THEN** the mate is added, the pin's axis lies on the hole's axis, and the reply names the faces used

#### Scenario: No face at the point
- **WHEN** the point is not on any face of the named component
- **THEN** the call fails with `not_found`, names the component and the point, and adds no mate

#### Scenario: Both kinds for one side
- **WHEN** a side gives both a named entity and a face point
- **THEN** the call fails with `invalid_input`

### Requirement: Fix, float, rigid and flexible components

A `set_component_state` tool SHALL fix or float a component of the active assembly, and make a sub-assembly rigid or flexible, changing nothing else about it.

#### Scenario: Float a component
- **WHEN** a fixed component is set `fixed: false`
- **THEN** it is floating, and the reply reads back `fixed: false`

#### Scenario: Flexible sub-assembly
- **WHEN** a sub-assembly is set `flexible: true`
- **THEN** its solving is flexible, and its suppression, visibility and referenced configuration are as before
