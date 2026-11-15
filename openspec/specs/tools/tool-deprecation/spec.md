# tools/tool-deprecation Specification

## Purpose
A tool replaced by another keeps working for one minor release, and says
what replaced it, so a client can move without breaking.
## Requirements
### Requirement: A deprecated tool keeps working and names its replacement
A tool at the `deprecated` level SHALL behave as before. Its description
SHALL open with "Deprecated: use `<replacement>`." (or "Deprecated: no
replacement." when there is none), and a successful result SHALL carry that
sentence as `warning`.

#### Scenario: Calling a deprecated tool
- **WHEN** an agent calls `load_part` with a valid part path
- **THEN** the part opens as before, and the result's `warning` is
  "Deprecated: use `open_model`."

#### Scenario: Reading its description
- **WHEN** a client lists the tools
- **THEN** `load_part`'s description starts "Deprecated: use `open_model`."
  and its tags include `level:deprecated`

### Requirement: A replacement covers what it replaces
A tool SHALL be deprecated only when its replacement accepts every input
the deprecated tool accepted, or the description names the other tool
that does the rest.

#### Scenario: save_assembly's reference copy
- **WHEN** `save_assembly` is deprecated in favour of `save_file`
- **THEN** its description says to use `pack_and_go_assembly` for a copy
  with the referenced parts

### Requirement: Deprecated tools are removed at the next major release
The support-level check SHALL fail when the package's major version is
higher than the one a tool was deprecated in and the tool is still
registered.

#### Scenario: Releasing 3.0.0
- **WHEN** the version is 3.0.0 and `load_part` (deprecated in 2.1.0) is
  still registered
- **THEN** the check fails and names `load_part`

