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

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e .
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
