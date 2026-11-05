# tools/tool-descriptions Specification

## Purpose
Every MCP tool tells an agent, before it is called, what it does, when to
use it over its siblings, what it needs, what it changes and what it
returns.
## Requirements
### Requirement: Descriptions follow one standard

Every registered tool's description SHALL say:

- what the tool does, in SolidWorks terms;
- when to use it, and which other tool to use instead, where tools overlap;
- what it needs (document type, selection, SolidWorks running);
- what it changes, or that it is read-only;
- what its success payload carries.

It SHALL NOT be a restatement of the tool's name, and SHALL fit in 1200
characters.

#### Scenario: A tool that overlaps another

- **WHEN** an agent reads the description of `get_mass_properties`
- **THEN** it says which of `get_mass_properties` and
  `calculate_mass_properties` to use

#### Scenario: A tool that only reads

- **WHEN** an agent reads the description of a tool that changes nothing
- **THEN** it says the tool is read-only

### Requirement: The input object is described

A tool that takes one `input_data` object SHALL describe that object
specifically: what it holds, and which fields are required. It SHALL NOT use
a generic description such as "The input data value." Every field inside
the input object SHALL have its own description.

#### Scenario: Reading a tool's schema

- **WHEN** a client lists the tools
- **THEN** no tool's `input_data` description is generic
- **AND** every field of every input object has a description

### Requirement: Behaviour hints on every tool

Every registered tool SHALL carry the MCP annotations `title`,
`readOnlyHint`, `destructiveHint` and `idempotentHint`. A tool that changes
nothing SHALL be read-only. A tool that deletes, overwrites or closes without
saving SHALL be destructive. Every tool SHALL also carry one family tag,
the name of the module that defines it.

#### Scenario: Listing the tools

- **WHEN** a client lists the tools
- **THEN** each tool has a title and the three hints
- **AND** `list_features` is read-only, and `delete_feature` is destructive
- **AND** `create_extrusion` is tagged `modeling`

### Requirement: The standard is checked

The test suite SHALL fail when a registered tool:

- has a description that breaks the standard;
- has a generic `input_data` description, or an input field without one;
- has no hints or no family tag.

#### Scenario: A new tool with a placeholder docstring

- **WHEN** a contributor registers a tool whose description is
  "Handle new thing."
- **THEN** the description check fails and names the tool

