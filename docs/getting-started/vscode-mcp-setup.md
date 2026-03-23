# VS Code MCP Setup

This guide shows complete beginners how to connect Visual Studio Code to the SolidWorks MCP server.

## What This Means

If you have never used AI tools before, this is the short version:

- VS Code is the editor where you write code and chat with GitHub Copilot.
- An MCP server is a helper process that gives the AI safe access to tools.
- The SolidWorks MCP server gives the AI SolidWorks-related tools such as sketching, drawing, export, and analysis commands.

Once this is working, you can ask Copilot to use SolidWorks tools from chat instead of only answering with text.

## Before You Start

Make sure these items are already done:

- You installed this project and its dependencies.
- You can start the server from this repository.
- You have VS Code installed.
- You have GitHub Copilot access in VS Code.
- If you want real SolidWorks automation, SolidWorks is installed on Windows.

If you have not done that yet, start with the [Installation Guide](installation.md).

## Choose the Setup That Matches You

| Your setup | What it is for | Recommended MCP type |
| --- | --- | --- |
| Windows only | Real SolidWorks automation on one machine | `stdio` |
| Linux / WSL only | Mock-mode development and testing | `stdio` |
| Linux / WSL client + Windows host | Real SolidWorks on Windows, editor on Linux/WSL | `http` |

## Step 1: Decide Where to Save the MCP Configuration

VS Code can store MCP servers in two places:

- User configuration: available in all VS Code workspaces for your account.
- Workspace configuration: saved in `.vscode/mcp.json` in this project.

For beginners, use user configuration first. It is easier to manage and does not change your repository files.

!!! info "Screenshot to add"
    Capture the VS Code Command Palette with `MCP: Open User Configuration` highlighted.
    Include:
    - The full command name in the Command Palette
    - The VS Code window title bar
    - Enough of the editor to show the user is in VS Code

## Step 2: Open the MCP Configuration File

In VS Code:

1. Open the Command Palette with `Ctrl+Shift+P`.
2. Type `MCP: Open User Configuration`.
3. Press `Enter`.
4. VS Code opens your user `mcp.json` file.

If you want project-only setup instead, create or open `.vscode/mcp.json` in this repository.

## Step 3: Paste the Configuration That Matches Your Setup

### Option A: Windows only

Use this when VS Code, the MCP server, and SolidWorks all run on the same Windows machine.

```json
{
  "servers": {
    "solidworks-mcp-server": {
      "type": "stdio",
      "command": "conda",
      "args": [
        "run",
        "-n",
        "solidworks_mcp",
        "python",
        "-m",
        "solidworks_mcp.server"
      ]
    }
  },
  "inputs": []
}
```

Use this only after you have created the `solidworks_mcp` Conda environment.

### Option B: Linux / WSL only

Use this when you only want development, docs, and tests.

If you store the config inside this repository as `.vscode/mcp.json`, use:

```json
{
  "servers": {
    "solidworks-mcp-server": {
   "type": "stdio",
   "command": "C:\\Windows\\System32\\wsl.exe",
   "args": [
    "-d",
    "Ubuntu-24.04",
    "--",
    "/home/andrew/.local/bin/micromamba",
    "run",
    "-n",
    "solidworks_mcp",
    "python",
    "-m",
    "solidworks_mcp.server"
   ]
  },
  "inputs": []
}
```

This path does not control the real SolidWorks desktop app.

### Option C: Linux / WSL client + Windows host

Use this when SolidWorks runs on Windows but VS Code or your editor session runs on Linux or WSL.

First, start the server on the Windows host:

```powershell
conda activate solidworks_mcp
python -m solidworks_mcp.server --mode remote --host 0.0.0.0 --port 8000
```

Then use this MCP configuration in VS Code on the client machine:

```json
{
  "servers": {
    "solidworks-mcp-server": {
      "type": "http",
      "url": "http://YOUR-WINDOWS-IP:8000"
    }
  },
  "inputs": []
}
```

Replace `YOUR-WINDOWS-IP` with the real IP address of the Windows machine.

!!! info "Screenshot to add"
    Capture the `mcp.json` editor with the SolidWorks server block visible.
    Include:
    - The file name `mcp.json`
    - The `solidworks-mcp-server` entry
    - The full command or URL line
    - VS Code JSON syntax highlighting if possible

## Step 4: Save the File and Trust the Server

After you save `mcp.json`, VS Code will detect the server.

You might see a trust prompt. Read it carefully and only continue if you trust this repository and the command you configured.

1. Save the file.
2. If prompted, choose to trust the server.
3. Wait a few seconds for VS Code to discover the tools.

!!! warning "Important"
    Local MCP servers can run code on your machine. Only do this for repositories and commands you trust.

!!! info "Screenshot to add"
    Capture the trust dialog for the MCP server.
    Include:
    - The server name
    - The command or URL being trusted
    - The trust / cancel buttons

## Step 5: Confirm the Server Is Running

Use one of these methods:

1. Open the Command Palette and run `MCP: List Servers`.
2. Select `solidworks-mcp-server`.
3. Check whether the server status is running.

You can also open Chat in VS Code and look for MCP tools from the server.

!!! info "Screenshot to add"
    Capture the MCP server list showing `solidworks-mcp-server`.
    Include:
    - The server name
    - Its current status
    - Any action menu items such as Start, Stop, or Show Output

## Step 6: Try a Simple Test Prompt

Start with a low-risk prompt like one of these:

- `List the SolidWorks tools available from the connected MCP server.`
- `Explain what the SolidWorks MCP server can do in plain English.`
- `Show me the available drawing-related SolidWorks tools.`

If you are on Windows with SolidWorks running, you can later try more active prompts such as:

- `Create a new part and start a sketch on the Front Plane.`
- `Create a technical drawing from the active model.`

## Troubleshooting

### The server does not appear in VS Code

Check these first:

- The JSON is valid.
- The server name is inside the `servers` object.
- The command actually exists on your machine.
- You saved the file after editing it.

Then run `MCP: List Servers` and choose `Show Output`.

### VS Code says the server failed to start

Common causes:

- The Conda environment does not exist yet.
- The package is not installed in that environment.
- `make` is not installed on Linux / WSL.
- The HTTP URL points to the wrong Windows IP address or port.

### The server starts, but SolidWorks actions fail

This usually means one of these is true:

- SolidWorks is not installed.
- SolidWorks is not running.
- You are on Linux / WSL and trying to use real COM automation locally.
- You intended to use the Windows host, but the server URL or host startup command is wrong.

## Good Next Steps

- Read the [Quick Start](quickstart.md) guide for first examples.
- Read [Platform and Connectivity](../user-guide/platform-connectivity.md) if you are using WSL or a remote Windows host.
- After VS Code is working, continue to [Claude Code MCP Setup](claude-code-setup.md) if you want the same server available there too.
