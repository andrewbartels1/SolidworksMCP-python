## Context

`pyproject.toml` installs a console script, `solidworks-mcp` (and the same
entry point as `solidworks-mcp-python`). It reads the config from the
environment, defaults to the real pywin32 adapter in local stdio mode, and
runs the same server start as `src/utils/start_local_server_claude.py`, the
launcher the README recommends today. Their differences:

- the launcher sets security MINIMAL, while the default is STANDARD. With
  no API key configured, STANDARD adds no checks over stdio;
- `--year` is only a hint for the API docs lookup, which otherwise detects
  the installed year;
- the launcher defaults to mock and needs `--real`; the console script
  defaults to real and takes `--mock`.

## Goals / Non-Goals

**Goals:** one launcher in every config; the README section fits on about
one screen per client when opened.

**Non-Goals:** changing how the server starts (only `setup` is routed
elsewhere); PyPI install.

## Decisions

- **Launcher: `.venv\Scripts\solidworks-mcp.exe`, no arguments.** It has no
  script path, no PowerShell and no flags to get wrong. It is also the
  command `uvx solidworks-mcp-python` runs after the PyPI release, so the
  configs change in one place later. Rejected:
  - `python.exe` with `start_local_server_claude.py --real` (two paths
    and a flag);
  - `run-mcp-claude.ps1` (PowerShell over stdio is the documented failure
    mode).
- **Collapsible `<details>` per client.** GitHub renders them, and a
  visitor opens only their own client. Rejected: one long section per
  client (the current wall).
- **Claude Code uses `claude mcp add`**: one command, not a JSON file.
- **Troubleshooting moves to `docs/getting-started/installation.md`.** The
  README keeps one link.

### The setup command

- **A subcommand, not a second script.** `cli_main` sends `setup ...` to
  the setup app; any other arguments start the server as before. After
  PyPI, `uvx solidworks-mcp-python setup` needs no `--from`.
- **typer + rich only.** Both are already dependencies. Choosing clients
  is a numbered prompt (`1,3` or `all`) rather than an arrow-key menu, so
  there's no new dependency and it works in any terminal.
- **One module per job** under `setup/`: `config_file` (safe JSON edit),
  `clients` (where each client keeps its config), `solidworks` (registry),
  `launcher` (the command to write), `handshake` (the start-up check), and
  `cli` (the wizard). Each is tested alone, with no real files outside a
  temp dir and no real registry.
- **Claude Desktop location.** Use the existing config, newest first:
  `Claude-Data\claude_*`, then `Packages\Claude_*\LocalCache\Roaming\Claude`,
  then `%APPDATA%\Claude`. With none, create it in the first of those whose
  parent folder exists.
- **Edit the parsed JSON, not the text.** The file is parsed, the one key is
  set, and the whole object is written back with `indent=2`. Other entries
  keep their keys, values and order, though their whitespace may change.
  JSON with comments (allowed by VS Code) fails to parse and is left
  untouched with a message, rather than having the comments stripped.
- **A timestamped backup** beside the file
  (`<name>.bak-YYYYMMDD-HHMMSS`), copied byte for byte so a second run
  never overwrites the original backup.
- **The start-up check runs the launcher with `--mock`**, so it proves the
  launcher and the stdio handshake without starting SolidWorks.
- **Claude Code uses its own CLI**: `claude mcp add --scope user`. If
  `claude` isn't on the PATH, the command prints the line to run.

## Risks / Trade-offs

- [Another client moves its config file again] → Each location is one
  entry in `clients.py`, and `--dry-run` shows the path before writing.
- [Re-running `install.ps1` while a client runs the server] → Windows
  locks the running `solidworks-mcp.exe`, and an install that tries to
  replace it stops partway, leaving packages half-removed (seen
  2026-10-31). The script first checks for programs running from `.venv`.
  If the server is already installed, it skips the install (the install is
  editable, so code changes are live) and goes on to setup; otherwise it
  stops and asks the user to quit their clients.
- [A config in use is changed while the client is running] → The write is
  atomic (temp file plus replace), and the command tells the user to
  restart the client.

- [The `.exe` behaves differently from the tested launcher in a real
  client] → Before the README changes, a live check in Claude Desktop must
  show the tools listed and `get_model_info` answering. If it fails, fall
  back to the `python.exe` + `start_local_server_claude.py --real` form in
  every config. The rule of one launcher everywhere still holds.
- [Old configs pointing at `run-mcp.ps1` keep working] → No launcher is
  removed; the docs page still describes them.
