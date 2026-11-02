## Why

The README's install and client setup is a wall of text: four client
configs use three different launchers, and the stdio and PowerShell
internals come before any config. A first-time visitor can't tell which
config to copy.

Hand-written configs also fail in practice. The maintainer's own Claude
Desktop setup failed (2026-10-31) for two reasons that written directions
can't fix:

- the README's placeholder path `C:\path\to\...` was pasted unchanged, so
  Claude Desktop could not start the server (`spawn ... ENOENT`);
- Claude Desktop now reads its config from a third location,
  `%LOCALAPPDATA%\Claude-Data\claude_<id>\`, which the README doesn't list.

## What Changes

- **A guided setup command, `solidworks-mcp setup`.** It:
  - finds the installed SolidWorks versions from the registry, and offers
    mock mode when there are none;
  - finds the MCP clients on the machine (Claude Desktop in all three
    config locations, Claude Code, VS Code, Cursor, LM Studio) and lets the
    user pick from a numbered list;
  - checks that the server starts and lists its tools before writing
    anything;
  - adds one `solidworks` entry with the absolute path of the installed
    launcher, so there is no path to type;
  - says what to restart and how to confirm the connection;
  - supports `--dry-run`, `--yes`, `--client` and `--remove`.
- **Other people's config files are handled with care.** Client config
  files often hold other servers' secrets. The command only ever changes the
  `solidworks` entry, never prints any other entry, backs the file up first,
  writes it atomically, and reads it back to check that it is valid JSON
  holding the new entry. A file that isn't valid JSON is left untouched,
  and the error names only the line and column.
- **A bootstrap script, `install.ps1`**: it creates the `.venv`, installs
  the package, and runs `solidworks-mcp setup`.
- One **Install** section replaces "What Works", "Requirements", "Quick
  Start" and "Common Windows Fixes": what you need, `install.ps1`, and how
  to know it worked.
- One **Connect your client** section replaces "MCP Client Configuration".
  It leads with `solidworks-mcp setup`, and keeps one collapsible block per
  client for manual setup. Every client launches the server the same way.
- The launcher notes move to a Troubleshooting section on the docs
  Installation page, linked from the README.
- Development commands and the local CI replica move under one
  **Contributing** heading near the end; the environment toggles fold into a
  collapsible block.

Out of scope:

- install from PyPI. After the 1.5.0 release, the same flow becomes
  `uvx solidworks-mcp-python setup`;
- the Spanish README;
- the `--selftest` health check (#179), which can reuse the setup command's
  start-up check.

## Capabilities

### New Capabilities

- `docs/readme-install`: the README gets a first-time user from nothing to a
  connected client with one install script and one setup command.
- `setup/client-setup`: a guided command that configures MCP clients for
  this server safely.

### Modified Capabilities

None.

## Impact

- New: `src/solidworks_mcp/setup/` (the setup command), its tests under
  `tests/solidworks_mcp/setup/`, and `install.ps1`.
- Changed:
  - `server.py`: `cli_main` routes `setup` to the setup command, and
    `solidworks-mcp` with no arguments still starts the server;
  - `README.md` and `docs/getting-started/installation.md`.
- No COM, adapter or tool code is touched.
