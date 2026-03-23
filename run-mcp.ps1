# PowerShell script to run SolidWorks MCP Server from Windows Python
$ErrorActionPreference = "Stop"

# Get the directory where this script is located
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
	Write-Error "Virtual environment python not found: $venvPython"
	exit 1
}

# Run the MCP server with the venv interpreter directly
& $venvPython -m solidworks_mcp.server
