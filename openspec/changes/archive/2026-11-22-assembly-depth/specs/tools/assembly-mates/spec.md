## MODIFIED Requirements

### Requirement: Fix, float, rigid and flexible components

A `set_component_state` tool SHALL fix or float a component of the active assembly, make a sub-assembly rigid or flexible, hide or show it (`visible`), and make it transparent or opaque (`transparent`), changing nothing else about it, and reply with each state read back.

#### Scenario: Float a component
- **WHEN** a fixed component is set `fixed: false`
- **THEN** it is floating, and the reply reads back `fixed: false`

#### Scenario: Flexible sub-assembly
- **WHEN** a sub-assembly is set `flexible: true`
- **THEN** its solving is flexible, and its suppression, visibility and referenced configuration are as before

#### Scenario: Hide a base to see the pins
- **WHEN** the base is set `visible: false`, then `visible: true`
- **THEN** it is hidden, then shown, and is fixed and resolved throughout

#### Scenario: Transparent
- **WHEN** a component is set `transparent: true`
- **THEN** it shows transparent and the reply reads it back
