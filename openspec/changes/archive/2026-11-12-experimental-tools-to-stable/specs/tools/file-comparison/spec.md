## ADDED Requirements

### Requirement: Two files on disk are compared, and the reply says that is all

`compare_drawing_versions` and `compare_templates` SHALL compare two files on
disk by content hash and size, and SHALL say in the reply that no SolidWorks
content (views, dimensions, properties) was compared. Each SHALL take a typed
input with both paths required. A path that does not exist SHALL fail with
`not_found`, naming it.

#### Scenario: The same template twice
- **WHEN** an agent compares a SolidWorks part template with a copy of itself
- **THEN** `identical` is true and `size_delta_bytes` is 0

#### Scenario: Two different templates
- **WHEN** an agent compares the default part template with the default assembly template
- **THEN** `identical` is false, and `size_delta_bytes` is the second file's size minus the first's

#### Scenario: Two saved versions of a drawing
- **WHEN** a drawing is saved, a view is added, and it is saved under a second name
- **THEN** `compare_drawing_versions` reports `identical: false`

### Requirement: Comparison switches that did nothing are refused

`compare_templates` SHALL refuse `comparison_type`, `comparison_depth`,
`include_properties`, `include_dimensions`, `include_materials` and
`generate_report` with `invalid_input`, as the input contract does for every
removed input.

#### Scenario: An old caller sends a switch
- **WHEN** an agent calls `compare_templates` with `include_properties: true`
- **THEN** the call fails with `invalid_input`, and the message says the tool compares the files only
