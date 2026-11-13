## ADDED Requirements

### Requirement: The new solid feature tools report the measured change
On success, `create_hole`, `create_shell`, `add_draft`, `create_rib` and
`pattern_linear` SHALL include the same `measured_change` block as
`create_extrusion`, under the same best-effort rule. `create_hole`,
`create_shell` and `create_rib` SHALL fail, removing nothing, when the
volume is unchanged.

#### Scenario: A hole off the body
- **WHEN** SolidWorks accepts a hole that removes no material
- **THEN** the call fails, says the hole changed no volume, and the hole
  feature is deleted so the tree is as before
