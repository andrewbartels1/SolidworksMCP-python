# Installation Guide

This guide documents the Windows setup path that was validated to work with real SolidWorks COM automation.

## Core Rule

Real SolidWorks automation requires Windows.

- Windows: real COM automation.
- Linux/WSL: mock-mode testing and docs workflows.

## 1. Install Python from python.org

1. Download Python 3.11+ from <https://www.python.org/downloads/windows/>.
2. Run installer.
3. Enable **Add python.exe to PATH**.
4. Finish install and open a new PowerShell window.

Verify:

```powershell
python --version
python -c "import sys; print(sys.executable)"
```

If `python` is not found or opens Microsoft Store, reinstall Python from python.org and confirm PATH option was enabled.

## 2. Clone Repository

```powershell
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python
```

## 3. Create venv and Install Package

### Option A: Core MCP server only

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[dev,test,docs]"
```

### Option B: Core + Prefab UI dashboard (recommended)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[dev,test,docs,ui]"
```

The `ui` extra installs `prefab-ui` and `fastapi` which are needed for `dev-ui-probe` and `dev-ui`.

!!! note "venv created from conda/micromamba Python"
    If you use `micromamba` (recommended for dev workflows), create the venv from the micromamba Python to ensure compatible binaries. After creating the venv, bootstrap pip if it is missing:

    ```powershell
    # Create venv from the micromamba solidworks_mcp env Python
    C:\Users\<you>\micromamba\envs\solidworks_mcp\python.exe -m venv .venv
    .\.venv\Scripts\python.exe -m ensurepip --upgrade
    .\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
    .\.venv\Scripts\python.exe -m pip install -e ".[dev,test,docs,ui]"
    ```

    Or use the all-in-one dev command after setup:

    ```powershell
    .\dev-commands.ps1 dev-install-ui
    ```

This installs both `solidworks_mcp` and runtime dependencies such as `fastmcp` in the same interpreter used by the MCP server.

## 4. Configure VS Code MCP

Open `%APPDATA%\Code\User\mcp.json` and configure:

```json
{
  "servers": {
    "solidworks-mcp-server": {
      "type": "stdio",
      "command": "powershell",
      "args": [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "C:\\path\\to\\SolidworksMCP-python\\run-mcp.ps1"
      ]
    }
  }
}
```

Set the script path to your local repository location.

## 5. Start and Verify

Start server:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-mcp.ps1
```

Healthy startup logs include:

- `Platform: Windows`
- `SolidWorks COM interface is available`
- `Registered 76 SolidWorks tools`
- `Connected to SolidWorks`

## Troubleshooting

### `ModuleNotFoundError: solidworks_mcp`

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

### `ModuleNotFoundError: fastmcp`

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

### SolidWorks connection problems

- Launch SolidWorks before starting MCP.
- Confirm you are running on Windows, not WSL for COM usage.
- Verify COM import:

```powershell
.\.venv\Scripts\python.exe -c "import win32com.client; print('win32com OK')"
```

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

### `prefab.exe` not found when running `dev-ui-probe` or `dev-ui`

!!! note "Install UI extras to get prefab-ui into .venv"
    **Error:** `Prefab executable not found: .venv\Scripts\prefab.exe`

    This means the `.venv` was created without the `ui` optional dependency group, or `pip` skipped writing the console-script wrapper on initial install.

    **Option 1 — Let `run-ui.ps1` fix it automatically:**

    `run-ui.ps1` detects when `prefab.exe` is missing and auto-reinstalls `prefab-ui` before starting. Just run:

    ```powershell
    .\dev-commands.ps1 dev-ui-probe
    ```

    **Option 2 — Use the UI install helper:**

    ```powershell
    .\dev-commands.ps1 dev-install-ui
    ```

    **Option 3 — Manual fix:**

    ```powershell
    .\.venv\Scripts\python.exe -m pip install --force-reinstall "prefab-ui>=0.19.0" "fastapi>=0.115.0" "uvicorn>=0.24.0"
    ```

    If `.venv\Scripts\python.exe` fails with **"No pyvenv.cfg file"**, the venv is corrupted. Delete and recreate it:

    ```powershell
    Remove-Item -Recurse -Force .venv
    python -m venv .venv
    .\.venv\Scripts\python.exe -m ensurepip --upgrade   # if pip missing (conda Python)
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
