# docs/tool-catalog Specification

## Purpose
TBD - created by archiving change tool-catalog-check. Update Purpose after archive.
## Requirements
### Requirement: Every tool has one catalog entry

Every registered tool SHALL have exactly one entry, a `### \`<name>\``
heading, on the catalog page of its family (the family tag with `_` as
`-`). No entry SHALL name a tool that isn't registered.

#### Scenario: A new tool without an entry
- **WHEN** a tool is registered and no catalog page has its heading
- **THEN** the catalog check fails and names the tool and the page it belongs on

#### Scenario: A removed tool's entry
- **WHEN** a page has an entry for a name no tool has
- **THEN** the check fails and names it

### Requirement: An entry matches the tool's inputs

An entry's parameter table SHALL list exactly the tool's input fields; a
tool without inputs says `**Parameters:** none`. Its sample call SHALL be
JSON that the tool's input model accepts.

#### Scenario: A field added to a tool
- **WHEN** a tool gains an input the entry's table doesn't list
- **THEN** the check fails and names the field

#### Scenario: A placeholder sample
- **WHEN** a sample call has `null` for a required field, or isn't valid JSON
- **THEN** the check fails with the validation error

