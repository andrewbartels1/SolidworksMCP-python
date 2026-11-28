## ADDED Requirements

### Requirement: The part's solid bodies, by name
`list_bodies` SHALL take no arguments and SHALL reply, for the active part,
with `bodies`, a list in the order SolidWorks gives them. Each entry SHALL carry `name`
(the name every body tool accepts), `volume_mm3` and `bounding_box_mm`, the
box's `min` and `max` corners `[x, y, z]` and its `size`. The reply SHALL
also carry `count` and `total_volume_mm3`. Only solid bodies are listed;
surface bodies are left out.

#### Scenario: Two blocks not merged
- **WHEN** a part holds a 40 × 40 × 10 mm block and a second
  20 × 20 × 30 mm block extruded with `merge_result: false`
- **THEN** `list_bodies` replies `count` 2, with each body's name, the
  volumes 16000 and 12000, and a `total_volume_mm3` of 28000

#### Scenario: A part with no body yet
- **WHEN** the active part has only sketches
- **THEN** `list_bodies` succeeds with `count` 0 and an empty `bodies`

### Requirement: Only on a part
`list_bodies` SHALL fail with `invalid_input` when no document is open or
the active document is an assembly or a drawing, and the message SHALL say
a part must be active.

#### Scenario: An assembly is active
- **WHEN** `list_bodies` is called with an assembly active
- **THEN** it fails with `invalid_input`, saying it reads a part's bodies
