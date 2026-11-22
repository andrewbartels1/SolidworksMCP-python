## ADDED Requirements

### Requirement: Explode an assembly automatically or step by step
`create_exploded_view` SHALL explode the active assembly's active
configuration and show it. With no `steps` it SHALL explode it
automatically. With `steps`, each moving named `components` a `distance`
(mm, above 0) along `x`, `y` or `z` (`reverse` for the other way), it SHALL
add one explode step per entry, in order. It SHALL reply with the exploded
view's name, its step count, and the assembly's bounding box before and
after.

#### Scenario: Pins lifted out of a base
- **WHEN** four 30 mm pins standing in an 8 mm base are exploded 40 mm
  along `y`
- **THEN** one step is added, the view shows exploded, and the bounding
  box's height grows by 40 mm

#### Scenario: A component that isn't there
- **WHEN** a step names `bolt-9`, which the assembly doesn't hold
- **THEN** it fails as `not_found`, listing the components it holds, and no
  step is added

### Requirement: Show the assembly exploded or collapsed
`set_exploded_view` SHALL show the active configuration's exploded view
(`exploded` true) or collapse it (false), and reply with the state read
back. With no exploded view it SHALL fail as `not_found`.

#### Scenario: Collapse and explode again
- **WHEN** an exploded assembly is set `exploded: false`, then `true`
- **THEN** its bounding box returns to the assembled size, then to the
  exploded size

### Requirement: A drawing view of the exploded assembly
`create_drawing_view` with `exploded` true SHALL show the assembly's
exploded view in the new drawing view, and say so in its reply.

#### Scenario: An exploded isometric view
- **WHEN** an isometric view of the exploded assembly is placed with
  `exploded: true`
- **THEN** the view shows the parts apart, as in the assembly's exploded
  view
