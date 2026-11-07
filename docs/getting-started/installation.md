# Installation Guide

Real SolidWorks automation needs Windows 10 or 11 with SolidWorks installed and opened at least once. Linux and WSL work for the docs, the tests and mock mode.

## 1. Install uv

[uv](https://docs.astral.sh/uv/) runs the server from PyPI and fetches Python 3.13 for it, so you don't need Python installed. In PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then open a new PowerShell window, so `uvx` is on the PATH. (`winget install --id=astral-sh.uv -e` works too.)

## 2. Connect your MCP clients

```powershell
uvx solidworks-mcp-python setup
```

The package is `solidworks-mcp-python`. `uvx solidworks-mcp` installs a different project.

Setup walks through:

1. **SolidWorks.** It reads the installed versions from the registry and starts the server with the newest one (`--year 2026`); `--year` picks another. With none found, it offers mock mode.
2. **Clients.** It lists Claude Desktop, Claude Code, VS Code, Cursor and LM Studio, with what it found for each, and you pick by number.
3. **A start-up check.** It starts the server once in mock mode and confirms that it lists its tools. SolidWorks isn't touched, and nothing is written if this fails.
4. **The entry.** It adds a `solidworks` entry that runs `uvx solidworks-mcp-python --year <year>`, with `uvx` by its full path, so it works whatever PATH the client starts it with. Run from a clone's `.venv`, it runs that `.venv`'s `solidworks-mcp.exe` instead. Claude Code is configured with `claude mcp add --scope user`.
5. **Older entries.** If a client has other entries that start this server the old way (`run-mcp.ps1`, `start_local_server_claude.py` and the like), it names them and offers to remove them, so tools don't load twice.
6. **Next steps.** It says what to restart in each client and how to confirm the connection.

| Option | What it does |
| --- | --- |
| `--client <name>` | Configure `claude-desktop`, `claude-code`, `vscode`, `cursor` or `lmstudio` without the list. Repeat it for several. |
| `--dry-run` | Show what would change, and change nothing. |
| `--yes` | Don't ask: configure every client found. Older entries are kept unless `--replace-old` is also given. |
| `--remove` | Take the `solidworks` entry out again. |
| `--replace-old` | Remove older entries for this server without asking. |
| `--mock` | Configure mock mode, which answers without SolidWorks. |
| `--year <year>` | The SolidWorks release to start the server with, e.g. `2026`. Default: the newest installed. Setup stops, changing nothing, if that year isn't installed. |
| `--skip-check` | Don't run the start-up check. |

### How setup treats your config files

Client config files often hold other servers' API keys and tokens, so setup:

- changes only the `solidworks` entry, or an older entry for this server that you agreed to remove;
- never prints or logs any other entry. The client list shows only file paths, and the `solidworks` entry's own command when it runs a different copy of the project;
- recognises older entries from their `command` and `args` alone, and never reads `env` or `headers`;
- backs the file up first, beside it, as `<name>.bak-YYYYMMDD-HHMMSS`;
- writes it in one step, as UTF-8 without a byte-order mark, and reads it back to check it is valid and holds the new entry;
- leaves a file that isn't valid JSON untouched, and reports only its line and column. VS Code's `mcp.json` may hold comments, which plain JSON doesn't allow, so remove them or add the entry by hand.

Nothing in the install or setup signs in to anything. The only download is the Python packages, from PyPI.

## 3. Check it works

Open SolidWorks, restart your client as setup told you, and ask *"What model is open in SolidWorks?"*. The server's log (VS Code shows it under the server's output; Claude Desktop writes `%LOCALAPPDATA%\Claude\Logs\mcp-server-solidworks.log`) includes:

- `SolidWorks COM interface is available`
- `Registered 155 SolidWorks tools` (the count grows as tools are added)
- `Connected to SolidWorks`

VS Code labels every line the server writes to stderr as `[warning]`. That is where its normal log goes, since stdout carries the MCP messages, so those labels aren't problems.

## Install from source

To work on the server itself, install it from a clone. You need [Python 3.13+](https://www.python.org/downloads/windows/), installed with **Add python.exe to PATH** ticked, and Git.

```powershell
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python
.\install.ps1
```

`install.ps1`:

1. finds Python 3.13+ (the `py` launcher first, then `python` on the PATH);
2. creates `.venv` in the project folder, if it doesn't exist;
3. installs the project into it, with `uv` if it's on the PATH, otherwise `pip`;
4. runs `solidworks-mcp setup`, which points your clients at this `.venv`.

Any options after `.\install.ps1` are passed on to setup, for example `.\install.ps1 --dry-run`. To run setup again later: `.\.venv\Scripts\solidworks-mcp.exe setup`.

The install is editable: code changes in the folder take effect the next time a client starts the server. For the development tools as well, run `.\.venv\Scripts\python.exe -m pip install -e ".[dev,test,docs]"`, or `.\dev-commands.ps1 dev-install` for the micromamba-based dev environment.

## Troubleshooting

### `uvx` is not recognized

Open a new PowerShell window after installing uv; the installer adds `%USERPROFILE%\.local\bin` to the PATH for new windows only. A client set up by hand that can't start `uvx` needs its full path as `command`, from `(Get-Command uvx).Source`. Setup always writes the full path.

### Getting a newer version

A client started with `uvx solidworks-mcp-python` keeps the version uv downloaded first. To move to the latest release, quit your clients, run `uv cache clean solidworks-mcp-python`, and start them again: the next start downloads the newest version.
### Re-running `install.ps1` while a client is using the server

Windows locks a running program, so an install can't replace `solidworks-mcp.exe` while Claude Desktop, VS Code or another client is running it. `install.ps1` checks first: if the server is installed and running, it skips the install and goes on to setup. To update dependencies after a `git pull`, quit your clients (Claude Desktop from the system tray) and run it again.

If an install was interrupted anyway and the server now fails with an `ImportError`, quit your clients and reinstall: `uv pip install --python .venv\Scripts\python.exe -e .` (or the `pip` equivalent). `uv pip check --python .venv\Scripts\python.exe` reports any package left half-installed.

### The client doesn't show the server

- **Claude Desktop** must be quit from the system tray, not just closed. It keeps its config in one of three places: `%LOCALAPPDATA%\Claude-Data\claude_<id>\` (current releases), `%LOCALAPPDATA%\Packages\Claude_<id>\LocalCache\Roaming\Claude\`, or `%APPDATA%\Claude\`. Setup picks the one in use. It also saves its preferences to that file, so a copy still running in the tray may write over the entry; if the entry is gone after a restart, quit Claude Desktop fully and run setup again.
- **VS Code**: run **MCP: List Servers** and start `solidworks`.
- Run `uvx solidworks-mcp-python setup --dry-run` to see each client's status, including whether its `solidworks` entry runs a different copy of the project, such as a test copy you have since deleted.

### Tools return simulated data

The server is in mock mode: its entry's `args` include `--mock`. Run setup again without `--mock`.

### `Could not connect to SolidWorks` in the log

SolidWorks wasn't running when the client started the server. Open SolidWorks, then restart the server from the client (for example **MCP: List Servers > solidworks > Restart** in VS Code). Despite the next log line, "Continuing with mock adapter for testing", the server does not switch to mock mode; its tools fail until it is restarted with SolidWorks open.

### SolidWorks connection problems

- Open SolidWorks before the client starts the server.
- Run on Windows, not WSL.
- Check COM: `.\.venv\Scripts\python.exe -c "import win32com.client; print('win32com OK')"`.
- The [troubleshooting runbook](https://github.com/andrewbartels1/SolidworksMCP-python/blob/main/CLAUDE.md#troubleshooting-runbook) covers COM errors in detail.

### Tool calls fail with `invalid_union` or "expected object, received string"

The client read something on the server's stdout that wasn't an MCP message. It happens with the older launchers:

- `deployment/run-mcp.ps1` and `src/utils/start_local_server.py` are a hands-on demo harness. They print banners to stdout, so they can't be used from a client config.
- `deployment/run-mcp-claude.ps1` and `src/utils/start_local_server_claude.py` are quiet, but go through PowerShell. A client starts servers with no console attached, which Windows PowerShell handles unreliably.

Run setup to replace the entry with `solidworks-mcp.exe`, which needs neither. It offers to remove the old entry too.

### `ModuleNotFoundError: solidworks_mcp` or `fastmcp`

The `.venv` the client starts isn't installed. Run `.\install.ps1` again, or install by hand: `.\.venv\Scripts\python.exe -m pip install -e .`.

### PowerShell execution policy blocks `dev-commands.ps1`

!!! note "Fix: set execution policy for your user"
    **Error:** `cannot be loaded because running scripts is disabled on this system`

    This is a Windows security default. Allow locally created scripts for your user only — no admin required:

    ```powershell
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
    ```

    Then retry `.\dev-commands.ps1 dev-help`.

    `RemoteSigned` lets local scripts run freely but still enforces signing for scripts downloaded from the internet. `CurrentUser` scope only affects your profile. Never set `Bypass` persistently — it disables all script security checks.

    For a one-time run without changing any policy (e.g. in CI):

    ```powershell
    powershell -NoProfile -ExecutionPolicy Bypass -File .\dev-commands.ps1 dev-help
    ```

### `micromamba` is not recognized when running `dev-install`

!!! note "Install micromamba on Windows PowerShell"
    **Error:** `micromamba : The term 'micromamba' is not recognized as the name of a cmdlet, function, script file, or operable program`

    `dev-install` uses micromamba to create the conda environment from `solidworks_mcp.yml`. Install it first:

    ```powershell
    Invoke-Expression ((Invoke-WebRequest -Uri https://micro.mamba.pm/install.ps1 -UseBasicParsing).Content)
    ```

    The installer will prompt for an install location (default is `%LOCALAPPDATA%\micromamba`) and ask whether to initialize the shell. **Answer yes** — this adds micromamba to your PowerShell profile so it is available in future sessions.

    If micromamba is still not recognized after reopening PowerShell, initialize it manually:

    ```powershell
    micromamba shell init -s powershell;
    micromamba activate base;
    ```

    Then close and reopen PowerShell. Verify it works:

    ```powershell
    micromamba --version
    ```

    Then retry:

    ```powershell
    .\dev-commands.ps1 dev-install
    ```

    If you prefer not to use micromamba, use the virtualenv path instead (no conda required):

    ```powershell
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
    .\.venv\Scripts\python.exe -m pip install -e ".[dev,test,docs,ui]"
    ```

### GitHub CLI (`gh`) not installed or not authenticated

!!! note "Install GitHub CLI and log in"
    `dev-test-full` uses `gh auth token` to resolve a GitHub token for smoke tests that call the GitHub API. If `gh` is missing or you are not logged in, those tests will be skipped or fail.

    **Step 1 — Install GitHub CLI on Windows:**

    Download and run the MSI installer from <https://cli.github.com/> (recommended for beginners), or install silently via winget:

    ```powershell
    winget install --id GitHub.cli
    ```

    **Step 2 — Reload your PATH without closing PowerShell:**

    After installation the `gh` command won't be found in the current window until the PATH is refreshed. Run:

    ```powershell
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
    ```

    Or simply close and reopen PowerShell. Verify it works:

    ```powershell
    gh --version
    ```

    **Step 3 — Authenticate:**

    ```powershell
    gh auth login
    ```

    At the prompts:

    1. Select **GitHub.com**
    2. Select **HTTPS**
    3. Select **Login with a web browser** — a code will be shown; paste it in the browser window that opens and approve

    Verify authentication succeeded:

    ```powershell
    gh auth status
    ```

    Once authenticated, `dev-test-full` will automatically pick up the token via `gh auth token`.
