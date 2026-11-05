# setup/client-setup Specification

## Purpose
`solidworks-mcp setup` connects the user's MCP clients to this server
without hand-editing any file, and without exposing or damaging anything
else in those files.
## Requirements
### Requirement: Clients are found, not typed

The command SHALL look for Claude Desktop (in its classic, packaged and
`Claude-Data` config locations), Claude Code, VS Code, Cursor and LM Studio.
It SHALL list them with what it found, and let the user choose which to
configure. With `--yes` it SHALL configure every client it found, and
`--client` SHALL choose clients by name.

#### Scenario: Claude Desktop keeps its config in the newest location

- **WHEN** the only Claude Desktop config is under
  `%LOCALAPPDATA%\Claude-Data\claude_<id>\`
- **THEN** the command writes to that file

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

### Requirement: Other entries are never changed or shown

The command SHALL change only the `solidworks` entry of a client's config.
It SHALL NOT print, log or reformat the values of any other entry. Before
changing a file, it SHALL back the file up. It SHALL write the file
atomically, as UTF-8 without a byte-order mark, and SHALL read it back to
confirm it is valid JSON that holds the new entry.

#### Scenario: Another server's secrets are in the file

- **WHEN** a config holds another server with an API key
- **THEN** that server's entry is the same after the command runs
- **AND** nothing the command prints contains the key

#### Scenario: The file is not valid JSON

- **WHEN** a client's config file can't be parsed
- **THEN** the command leaves the file untouched
- **AND** it reports the file, the line and the column, but not the content

### Requirement: The server is checked before anything is written

Before writing any config, the command SHALL start the launcher in mock
mode, complete the MCP handshake, and confirm that tools are listed. If the
check fails, it SHALL write nothing and say why. The check SHALL NOT start
or touch SolidWorks.

#### Scenario: The launcher doesn't start

- **WHEN** the start-up check fails
- **THEN** no config file is changed and the command exits with an error

### Requirement: Older entries for this server are offered for removal

The command SHALL find other entries in a client's config that start this
server with an older launcher (`run-mcp.ps1`, `run-mcp-claude.ps1`,
`start_local_server*.py`, `python -m solidworks_mcp.server`, or a
`solidworks-mcp` executable). It SHALL decide from each entry's `command`
and `args` only, and SHALL NOT read or print its `env`, `headers` or other
fields. It SHALL name each one found, with the program it launches, and
remove it only when the user agrees, or when `--replace-old` is given. With
`--yes` and no `--replace-old`, it SHALL keep them and say how to remove
them.

#### Scenario: VS Code still has a hand-made PowerShell entry

- **WHEN** VS Code's config has `solidworks-mcp-server` launching
  `run-mcp.ps1` through PowerShell, and the user accepts
- **THEN** that entry is removed, the new `solidworks` entry is kept
- **AND** every other server is unchanged

#### Scenario: Another vendor's SolidWorks server

- **WHEN** a config has a server for a different SolidWorks MCP project
- **THEN** it is not offered for removal

### Requirement: Setup can be previewed and undone

`--dry-run` SHALL report what would change and change nothing. `--remove`
SHALL delete only the `solidworks` entry from the chosen clients.

#### Scenario: Removing the server

- **WHEN** a user runs `solidworks-mcp setup --remove --yes`
- **THEN** the `solidworks` entry is gone from each client it was in
- **AND** every other entry is unchanged

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

