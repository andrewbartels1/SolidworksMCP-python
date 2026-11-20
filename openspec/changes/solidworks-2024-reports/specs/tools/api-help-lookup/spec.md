## ADDED Requirements

### Requirement: The index is saved in a folder the user can write to
The API lookups SHALL save a built index in the user's own data folder
(`~/.solidworks_mcp/docs-index`), not a folder relative to the server's
working directory, and SHALL still read an index saved in the old relative
folders.

#### Scenario: Started by Claude Desktop through uvx
- **WHEN** the server's working folder is not writable and
  `lookup_api_method` is called
- **THEN** the index is built and saved under `~/.solidworks_mcp/docs-index`
  and the lookup answers

#### Scenario: An index from before
- **WHEN** an index already exists in `.generated/docs-index`
- **THEN** lookups read it without rebuilding
