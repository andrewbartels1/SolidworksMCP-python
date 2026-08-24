# PowerShell script to run SolidWorks MCP Server from Windows Python
# This is a thin wrapper around start_local_server.py to provide a single entry point.
#
# Usage:
#   .\run-mcp.ps1 --real --year 2026        -- RECOMMENDED: real SolidWorks COM adapter
#   .\run-mcp.ps1 --real --year 2026 --log-level DEBUG  -- real mode with verbose logging
#   .\run-mcp.ps1                           -- mock mode (simulated responses, no SolidWorks)
#
# WARNING: Without --real the server runs in MOCK MODE.  Every tool call returns simulated
#          data (blank images, nonsense mass properties).  Nothing touches SolidWorks at all.
#
# PREREQUISITE: Open SolidWorks BEFORE restarting the server.  The adapter connects to an
#               already-running SLDWORKS.exe at startup and will not launch it for you.
#
# mcp.json example (Claude Code / VS Code):
#   "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\\run-mcp.ps1",
#            "--real", "--year", "2026"]

# Get the directory where this script is located. This must succeed before
# anything else, including $ErrorActionPreference, so the boot trace below
# can always find a writable location next to the script itself - see
# CLAUDE.md runbook item 9a for why %TEMP%/cwd cannot be trusted when this
# is spawned by an MCP host.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$bootTracePath = Join-Path $scriptDir "src\utils\solidworks_mcp_boot_trace.log"

function Write-BootTrace {
	param([string]$Message)
	try {
		$timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss.fff")
		Add-Content -Path $bootTracePath -Value "$timestamp [run-mcp.ps1] pid=$PID $Message" -Encoding utf8 -ErrorAction Stop
	}
	catch {
		# Never let tracing itself take down the server.
	}
}

Write-BootTrace "script started; scriptDir=$scriptDir; args=$($args -join ' ')"

trap {
	Write-BootTrace "UNHANDLED ERROR: $($_.Exception.GetType().FullName): $($_.Exception.Message)"
	Write-BootTrace "at: $($_.InvocationInfo.PositionMessage -replace '\r?\n', ' | ')"
	Write-BootTrace "stack: $($_.ScriptStackTrace -replace '\r?\n', ' | ')"
	break
}

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
$startServerScript = Join-Path $scriptDir "src\utils\start_local_server.py"

function Test-PythonExecutable {
	param(
		[string]$PythonPath
	)

	if (-not (Test-Path $PythonPath)) {
		Write-BootTrace "Test-PythonExecutable: not found at $PythonPath"
		return $false
	}

	try {
		& $PythonPath -c "import sys" | Out-Null
		$ok = $LASTEXITCODE -eq 0
		Write-BootTrace "Test-PythonExecutable: ran $PythonPath -c 'import sys', exitcode=$LASTEXITCODE, ok=$ok"
		return $ok
	}
	catch {
		Write-BootTrace "Test-PythonExecutable: exception invoking $PythonPath : $($_.Exception.Message)"
		return $false
	}
}

function Get-UvExecutable {
	$candidatePaths = @(
		(Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
		(Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe"),
		(Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe"),
		(Join-Path $env:APPDATA "Python\Scripts\uv.exe"),
		(Join-Path $scriptDir ".venv\Scripts\uv.exe")
	)

	$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
	if ($uvCommand -and $uvCommand.Source) {
		return $uvCommand.Source
	}

	foreach ($candidatePath in $candidatePaths) {
		if ($candidatePath -and (Test-Path $candidatePath)) {
			return $candidatePath
		}
	}

	return $null
}

Write-BootTrace "checking startServerScript at $startServerScript"
if (-not (Test-Path $startServerScript)) {
	Write-BootTrace "FATAL: start server script not found: $startServerScript"
	Write-Error "Start server script not found: $startServerScript"
	exit 1
}

Write-BootTrace "checking venv python at $venvPython"
if (Test-PythonExecutable $venvPython) {
	Write-BootTrace "launching: $venvPython $startServerScript $($args -join ' ')"
	& $venvPython $startServerScript @args
	Write-BootTrace "venv python process exited with code $LASTEXITCODE"
	exit $LASTEXITCODE
}

Write-BootTrace "venv python not usable, checking for uv"
$uvExecutable = Get-UvExecutable
if ($uvExecutable) {
	Write-BootTrace "launching via uv: $uvExecutable run --project $scriptDir python $startServerScript $($args -join ' ')"
	& $uvExecutable run --project $scriptDir python $startServerScript @args
	Write-BootTrace "uv-launched python process exited with code $LASTEXITCODE"
	exit $LASTEXITCODE
}

Write-BootTrace "FATAL: no usable python runtime found (checked venv and uv)"
Write-Error "No usable Python runtime found. Checked $venvPython and uv. Recreate the environment with 'uv venv' and reinstall dependencies if needed."
exit 1
