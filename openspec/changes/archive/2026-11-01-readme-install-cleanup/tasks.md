## 1. Check the launcher

- [x] 1.1 Locally: `.venv\Scripts\solidworks-mcp.exe` starts, writes
      nothing to stdout before the JSON-RPC handshake, and lists the tools
      (an MCP `initialize` + `tools/list` over stdio)
- [x] 1.2 Live, with the maintainer: `solidworks-mcp setup` configures
      the clients, which list the tools, and `get_model_info` answers
      from SolidWorks (2026-10-31: fresh copy via `install.ps1`; VS Code
      connected, 154 tools, read the open `monitor_stand_assemb` assembly)

## 2. Setup command

- [x] 2.1 `setup/config_file.py`: read without echoing, change only the
      `solidworks` entry, back up, write atomically without a BOM, read back
      and check; tests include another server's secret surviving unprinted
- [x] 2.2 `setup/clients.py`: find the clients and their config paths (all
      three Claude Desktop locations); `setup/solidworks.py`: installed
      versions from the registry
- [x] 2.3 `setup/launcher.py`: the absolute launcher command;
      `setup/handshake.py`: the mock-mode start-up check
- [x] 2.4 `setup/cli.py`: the wizard, `--dry-run`, `--yes`, `--client`,
      `--remove`, `--mock`; `cli_main` routes `setup`; Claude Code through
      `claude mcp add`
- [x] 2.5 `install.ps1`: venv, install, run setup
- [x] 2.6 Full mock suite, lint, 100 % coverage
- [x] 2.7 `setup/legacy.py`: recognise older entries for this server from
      `command`/`args` only; setup offers to remove them (`--replace-old`),
      never another vendor's server; tests, lint, coverage
- [x] 2.9 Name the launcher an entry pointed at before, when setup
      changes it, and flag an entry that runs a different copy
- [x] 2.8 `install.ps1` skips the install while the server is running
      from `.venv` (a locked `.exe` left packages half-removed)

## 3. README

- [x] 3.1 Install section: needs, `install.ps1`, what working looks like,
      and the two common fixes in one line each
- [x] 3.2 Connect your client: `solidworks-mcp setup` first, then a
      `<details>` entry each for manual setup of Claude Desktop, Claude Code,
      VS Code and LM Studio, all launching the `.exe`
- [x] 3.3 Contributing heading for development commands and the CI replica;
      the environment toggles in a collapsible block

## 4. Docs

- [x] 4.1 `installation.md`: the setup command, and Troubleshooting (the
      launcher notes, `invalid_union`, PowerShell over stdio, mock mode)
- [x] 4.2 `mkdocs build --strict` passes; README links resolve
- [x] 4.3 The other docs pages that describe the old launchers (quickstart,
      Claude Code setup,
      VS Code MCP setup, the docs home page, platform connectivity) point
      at `install.ps1` and `solidworks-mcp setup`
- [x] 4.4 Delete the project `.mcp.json`: its PowerShell entry would load
      every tool a second time beside the user-level entry setup adds
