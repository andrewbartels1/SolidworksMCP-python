## MODIFIED Requirements

### Requirement: The entry launches the installed server

The `solidworks` entry SHALL start the launcher that the command itself was
installed with, by absolute path. When the command runs from a temporary
`uvx` environment, the entry SHALL instead start `uvx` by absolute path
with the argument `solidworks-mcp-python`, so it keeps working after uv's
cache is cleaned. When no SolidWorks install is found, the command SHALL
offer a mock-mode entry instead. A real (not mock) entry SHALL pass
`--year <year>`: the year given to `setup --year`, else the newest
installed SolidWorks year. A mock entry SHALL NOT pass a year.

#### Scenario: A fresh install

- **WHEN** a user runs `solidworks-mcp setup` from a new `.venv`
- **THEN** each configured client starts that `.venv`'s `solidworks-mcp.exe`

#### Scenario: Setup run through uvx

- **WHEN** a user runs `uvx solidworks-mcp-python setup`
- **THEN** each configured client starts `uvx` by its absolute path, with
  the arguments `solidworks-mcp-python` and then `--year <year>`, or
  `--mock` for a mock entry
- **AND** no entry names a path inside uv's cache

#### Scenario: The entry ran a different copy

- **WHEN** a client's `solidworks` entry starts a launcher other than the
  one setup is running from
- **THEN** the client list says which launcher it runs now
- **AND** after updating it, setup names the launcher it replaced

#### Scenario: The year is written for you

- **WHEN** SolidWorks 2026 and 2024 are installed and the user runs
  `setup` without `--year`
- **THEN** each real entry's arguments end with `--year 2026`

#### Scenario: A year that isn't installed

- **WHEN** the user runs `setup --year 2025` and only SolidWorks 2026 is
  installed
- **THEN** setup says 2025 isn't installed, names 2026, and changes no
  config

## ADDED Requirements

### Requirement: The server is started with its SolidWorks year

The server SHALL accept `--year <YYYY>`, naming the SolidWorks release it
works with, and SHALL use it as the configured year. Started for real
SolidWorks without a year from `--year` or configuration, the server SHALL
log one warning saying how to add it, and SHALL keep working with the
newest installed SolidWorks. Mock mode SHALL NOT warn.

#### Scenario: Started with a year

- **WHEN** the server starts with `--year 2026`
- **THEN** its configured SolidWorks year is 2026 and no year warning is
  logged

#### Scenario: An entry written before --year existed

- **WHEN** the server starts for real SolidWorks with no year
- **THEN** it logs a warning naming `--year` and `setup`, and starts
