# Claude Code MCP Setup

This guide shows complete beginners how to connect Claude Code to the SolidWorks MCP server.

## What This Means

If you have never used Claude Code before, here is the simple version:

- Claude Code is a coding tool that runs in the terminal.
- MCP lets Claude Code connect to external tool servers.
- The SolidWorks MCP server gives Claude Code access to SolidWorks-related tools.

Once this is configured, Claude Code can discover and use the SolidWorks tools exposed by this project.

## Before You Start

Make sure these items are already done:

- You installed Claude Code.
- You can run the `claude` command in a terminal.
- You installed this project and its dependencies.
- If you want real SolidWorks automation, SolidWorks is installed on Windows.

If you have not done that yet, start with the [Installation Guide](installation.md).

## Choose the Setup That Matches You

| Your setup | What it is for | Recommended MCP type |
| --- | --- | --- |
| Windows only | Real SolidWorks automation on one machine | `stdio` |
| Linux / WSL only | Mock-mode development and testing | `stdio` |
| Linux / WSL client + Windows host | Real SolidWorks on Windows, Claude Code on Linux/WSL | `http` |

## Step 1: Open a Terminal in This Project

Claude Code project-scoped MCP servers are easiest for beginners because the configuration can live in the project itself.

1. Open a terminal.
2. Change into this repository folder.
3. Confirm the `claude` command works.

```bash
claude --version
```

!!! info "Screenshot to add"
    Capture the terminal showing the repository path and a successful `claude --version` command.
    Include:
    - The current working directory
    - The command that was run
    - The version output

## Step 2: Add the SolidWorks MCP Server

### Option A: Windows only (recommended)

Use this when Claude Code, the MCP server, and SolidWorks all run on the same Windows machine.

Run this from the project root:

```powershell
claude mcp add --transport stdio --scope project solidworks-mcp -- powershell -NoProfile -ExecutionPolicy Bypass -File .\run-mcp.ps1
```

Why this command uses `cmd /c`:

- On Windows, this is the safest beginner-friendly way to launch the local command through Claude Code.
- It avoids common command resolution problems in terminal environments.

### Option B: Linux / WSL only

Use this for mock-mode development, docs, and tests.

```bash
claude mcp add --transport stdio --scope project solidworks-mcp -- make run
```

This path does not control the real SolidWorks desktop app.

### Option C: Linux / WSL client + Windows host

1. Start the MCP server on the Windows host:

```powershell
.\.venv\Scripts\python.exe -m solidworks_mcp.server --mode remote --host 0.0.0.0 --port 8000
```

1. On the Linux / WSL side, add the remote server:

```bash
claude mcp add --transport http --scope project solidworks-mcp http://YOUR-WINDOWS-IP:8000
```

Replace `YOUR-WINDOWS-IP` with the actual IP address of the Windows machine.

!!! info "Screenshot to add"
    Capture the terminal right after `claude mcp add ...` succeeds.
    Include:
    - The exact add command that was used
    - The server name `solidworks-mcp`
    - The success message from Claude Code

## Step 3: Verify the Server Was Added

Run:

```bash
claude mcp list
```

You should see `solidworks-mcp` in the list.

You can also inspect the server details:

```bash
claude mcp get solidworks-mcp
```

If you used `--scope project`, Claude Code may also create or update a `.mcp.json` file in the project root.

!!! info "Screenshot to add"
    Capture the output of `claude mcp list`.
    Include:
    - The server name
    - The transport type (`stdio` or `http`)
    - Any status information shown by Claude Code

## Step 4: Check the Server Inside Claude Code

Start Claude Code in the project:

```bash
claude
```

Then type:

```text
/mcp
```

This opens the MCP server list inside Claude Code.

Look for `solidworks-mcp` and confirm it is available.

!!! info "Screenshot to add"
    Capture the `/mcp` screen in Claude Code.
    Include:
    - The `solidworks-mcp` server name
    - Its status
    - Any available actions such as authenticate, refresh, or remove

## Step 5: Try a Safe Beginner Prompt

Start with a simple prompt that does not change anything:

- `List the SolidWorks tools currently available from MCP.`
- `Explain what the SolidWorks MCP server can do for a beginner.`
- `Show me the drawing-related tools from the SolidWorks server.`

If you are on a real Windows SolidWorks setup, you can then try:

- `Create a new part and explain each step before using any tool.`
- `Create a simple hole tutorial workflow and describe what happened.`

## Step 6: Understand Where Claude Code Saves MCP Config

Claude Code can save MCP servers in different places:

- `--scope local`: private to you for this project
- `--scope project`: shared in the repository through `.mcp.json`
- `--scope user`: available across projects for your user account

For beginners, `--scope project` is the easiest to understand because the config stays with the project.

## Troubleshooting

### `claude` command is not found

Claude Code is not installed correctly or is not on your `PATH` yet.

### The MCP server was added, but it does not start

Common causes:

- The `.venv` environment is missing or incomplete.
- The project dependencies are not installed.
- `make` is not installed on Linux / WSL.
- The Windows host server is not actually running for the HTTP setup.

### Claude Code cannot reach the Windows host

Check these items:

- The Windows machine is running the remote MCP server.
- The Windows firewall allows the chosen port.
- You used the correct Windows IP address.
- You did not leave `localhost` in the command when Claude Code is running on a different machine.

### I want to remove the server and try again

Use:

```bash
claude mcp remove solidworks-mcp
```

Then re-run the correct `claude mcp add ...` command.

## Optional: What the Project `.mcp.json` File Looks Like

If you use `--scope project`, Claude Code may create a `.mcp.json` file in the repository root.

A typical `stdio` example looks like this:

```json
{
  "mcpServers": {
    "solidworks-mcp": {
      "command": "cmd",
      "args": [
        "/c",
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ".\\run-mcp.ps1"
      ]
    }
  }
}
```

A typical remote HTTP example looks like this:

```json
{
  "mcpServers": {
    "solidworks-mcp": {
      "type": "http",
      "url": "http://YOUR-WINDOWS-IP:8000"
    }
  }
}
```

## Good Next Steps

- If you have not already done it, set up [VS Code MCP](vscode-mcp-setup.md) too.
- Use the [Quick Start](quickstart.md) guide for beginner-friendly examples.
- Use [Platform and Connectivity](../user-guide/platform-connectivity.md) if your editor and SolidWorks are on different machines.
