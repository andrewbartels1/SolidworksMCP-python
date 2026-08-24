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
# NOTE FOR MCP HOST CONFIGS (Claude Desktop, VS Code, LM Studio): prefer pointing
# the host directly at ".venv\Scripts\python.exe" with "src\utils\start_local_server.py"
# as the script argument instead of this wrapper. MCP hosts spawn servers over raw
# stdio pipes with no console attached, and Windows PowerShell's native-command
# invocation has been observed to misbehave in exactly that scenario (see CLAUDE.md
# runbook item 9b) even though this script works fine from an interactive terminal.
# This wrapper is still useful for manual terminal use, since it auto-detects the
# venv (or falls back to uv) instead of requiring a hardcoded python.exe path.
#
# mcp.json example (Claude Code / VS Code) if you do use this wrapper:
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

	# NOTE: do not invoke this via PowerShell's own pipeline/redirection
	# engine (`| Out-Null`, `*>$null`, `2>&1`, etc). When there is no real
	# console attached to the host process - exactly the case when an MCP
	# client (Claude Desktop, VS Code, LM Studio) spawns this script over
	# raw stdio pipes with no pty - PowerShell's native-command invocation
	# misbehaves in this class of scenario: `| Out-Null` throws "Cannot run
	# a document in the middle of a pipeline", and even `*>$null`
	# redirection has been observed to silently leave $LASTEXITCODE unset
	# instead of throwing. Start-Process bypasses PowerShell's pipeline
	# engine entirely and goes straight to Win32 CreateProcess, which does
	# not have this problem. See CLAUDE.md runbook item 9b.
	$stdoutFile = $null
	$stderrFile = $null
	try {
		$stdoutFile = [System.IO.Path]::GetTempFileName()
		$stderrFile = [System.IO.Path]::GetTempFileName()
		$proc = Start-Process -FilePath $PythonPath -ArgumentList @('-c', '"import sys"') `
			-NoNewWindow -Wait -PassThru `
			-RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
		$ok = $proc.ExitCode -eq 0
		Write-BootTrace "Test-PythonExecutable: Start-Process $PythonPath -c 'import sys', exitcode=$($proc.ExitCode), ok=$ok"
		return $ok
	}
	catch {
		Write-BootTrace "Test-PythonExecutable: exception invoking $PythonPath : $($_.Exception.Message)"
		return $false
	}
	finally {
		if ($stdoutFile) { Remove-Item $stdoutFile -ErrorAction SilentlyContinue }
		if ($stderrFile) { Remove-Item $stderrFile -ErrorAction SilentlyContinue }
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
