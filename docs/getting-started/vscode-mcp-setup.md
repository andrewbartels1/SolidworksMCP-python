# VS Code MCP Setup

## Connect with setup

```powershell
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python
.\install.ps1
```

When setup lists your clients, pick **VS Code**. If the project is already installed, run just the setup:

```powershell
.\.venv\Scripts\solidworks-mcp.exe setup --client vscode
```

Setup adds a `solidworks` server to your user `%APPDATA%\Code\User\mcp.json`, leaving your other servers alone. It also offers to remove older entries for this server, such as one that runs `run-mcp.ps1` through PowerShell.

## Or add it by hand

Run **MCP: Open User Configuration** from the Command Palette (`Ctrl+Shift+P`) and add:

```json
{
  "servers": {
    "solidworks": {
      "type": "stdio",
      "command": "C:\\path\\to\\SolidworksMCP-python\\.venv\\Scripts\\solidworks-mcp.exe",
      "args": []
    }
  }
}
```

Use the full path to the `.venv` in your copy of the project. For mock mode, which needs no SolidWorks, use `"args": ["--mock"]`.

<details>
<summary><b>Linux/WSL: mock mode only</b></summary>

Use this for docs, tests or mock-mode development; it can't drive SolidWorks.

```json
{
  "servers": {
    "solidworks": {
      "type": "stdio",
      "command": "C:\\Windows\\System32\\wsl.exe",
      "args": [
        "-d",
        "YOUR_WSL_DISTRO",
        "--",
        "/home/YOUR_USERNAME/.local/bin/micromamba",
        "run",
        "-n",
        "solidworks_mcp",
        "python",
        "-m",
        "solidworks_mcp.server",
        "--mock"
      ]
    }
  }
}
```

</details>

## Check it works

Open SolidWorks, then run **MCP: List Servers** and start (or restart) `solidworks`. Its output should include:

- `SolidWorks COM interface is available`
- `Connected to SolidWorks`
- `Discovered 154 tools` (the count grows as tools are added)

VS Code labels every line the server writes to stderr as `[warning]`. That is the server's normal log, so those labels aren't problems.

## Troubleshooting

- **`Could not connect to SolidWorks`**: SolidWorks wasn't open when the server started. Open it, then restart `solidworks` from **MCP: List Servers**.
- **Tools return simulated data**: the entry has `"args": ["--mock"]`. Run setup again without `--mock`.
- **The same tools appear twice**: an older entry for this server is still in `mcp.json`. Run setup again and accept removing it.
- **`ModuleNotFoundError`**: run `.\install.ps1` again.

More fixes are in the [Installation guide's Troubleshooting](installation.md#troubleshooting).
