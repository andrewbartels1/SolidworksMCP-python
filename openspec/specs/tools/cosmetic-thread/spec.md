# tools/cosmetic-thread Specification

## Purpose
`add_cosmetic_thread` marks a cylindrical edge as threaded, so the thread
shows in drawings without modelling its helix.
## Requirements
### Requirement: A thread on a circular edge
`add_cosmetic_thread` SHALL take `edge_point`, `[x, y, z]` in millimetres
on a circular edge of the active part, `standard` (`iso` or `ansi_inch`),
`size`, and either `depth` in millimetres or `through: true`. It SHALL add
one cosmetic thread feature on that edge and reply with its name. The
part's volume SHALL be unchanged.

#### Scenario: A thread on a shaft end
- **WHEN** a Ø10 mm shaft is active and `add_cosmetic_thread` is called
  with a point on its end edge, `iso`, `M10` and `depth` 15
- **THEN** a cosmetic thread feature appears under the shaft's feature,
  and the volume is unchanged

### Requirement: The edge must be circular
When `edge_point` is not on a circular edge, `add_cosmetic_thread` SHALL
fail with `invalid_input`, name the point, and add nothing.

#### Scenario: A straight edge
- **WHEN** `edge_point` is on a straight edge of a block
- **THEN** the call fails with `invalid_input` saying the edge is not
  circular

