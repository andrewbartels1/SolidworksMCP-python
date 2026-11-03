## MODIFIED Requirements

### Requirement: The entry launches the installed server

The `solidworks` entry SHALL start the launcher that the command itself was
installed with, by absolute path. When the command runs from a temporary
`uvx` environment, the entry SHALL instead start `uvx` by absolute path
with the argument `solidworks-mcp-python`, so it keeps working after uv's
cache is cleaned. When no SolidWorks install is found, the command SHALL
offer a mock-mode entry instead.

#### Scenario: A fresh install

- **WHEN** a user runs `solidworks-mcp setup` from a new `.venv`
- **THEN** each configured client starts that `.venv`'s `solidworks-mcp.exe`

#### Scenario: Setup run through uvx

- **WHEN** a user runs `uvx solidworks-mcp-python setup`
- **THEN** each configured client starts `uvx` by its absolute path, with
  the arguments `solidworks-mcp-python` (and `--mock` for a mock entry)
- **AND** no entry names a path inside uv's cache

#### Scenario: The entry ran a different copy

- **WHEN** a client's `solidworks` entry starts a launcher other than the
  one setup is running from
- **THEN** the client list says which launcher it runs now
- **AND** after updating it, setup names the launcher it replaced
