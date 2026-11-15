# tools/stl-export Specification

## Purpose
`export_stl` writes the active part or assembly as an STL file through
SolidWorks' export call with its STL options, so a multibody part or an
assembly comes out as one merged file.
## Requirements
### Requirement: STL export uses its export options without a type mismatch
`export_stl` SHALL write the file with SolidWorks' STL export options (bodies
merged into one file), and SHALL NOT log a type-mismatch warning on the way.
A fallback without the options SHALL be used only when the first call
writes nothing, and the reply SHALL say when it was used.

#### Scenario: A single-body part
- **WHEN** `export_stl` writes a part with one body
- **THEN** the file exists, is non-empty, and no type-mismatch warning is
  logged

#### Scenario: The export call writes nothing
- **WHEN** the export with options returns without writing the file
- **THEN** the fallback writes it, and the reply's `warning` says the STL
  options were not applied

