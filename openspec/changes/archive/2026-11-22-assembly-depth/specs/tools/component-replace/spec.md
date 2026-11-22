## ADDED Requirements

### Requirement: Swap a component for another part
`replace_component` SHALL take a `component`, the `file_path` of the part
or assembly to put in its place, and `all_instances` (default off). It SHALL
replace that instance, or every instance of the same file, keep the mates
that still fit, and reply with the components before and after and each
replaced one's file read back.

#### Scenario: Short pins swapped for long ones
- **WHEN** a 30 mm pin with three patterned copies is replaced, all
  instances, by a 45 mm pin
- **THEN** all four pins are the 45 mm part and the assembly is 15 mm
  taller

#### Scenario: A file that doesn't exist
- **WHEN** `file_path` names no file
- **THEN** it fails as `invalid_input` naming the path, and nothing changes
