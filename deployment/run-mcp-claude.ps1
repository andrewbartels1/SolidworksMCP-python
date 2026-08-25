# PowerShell script to run the SolidWorks MCP server for MCP hosts (Claude
# Desktop, Claude Code, VS Code, LM Studio). Thin wrapper around
# start_local_server_claude.py, a minimal stdio-only entrypoint with no
# decorative output - see run-mcp.ps1 / start_local_server.py for the plain
# local dev/demo harness instead.
#
# Usage:
#   .\run-mcp-claude.ps1 --real --year 2026        -- RECOMMENDED: real SolidWorks COM adapter
#   .\run-mcp-claude.ps1 --real --year 2026 --log-level DEBUG  -- real mode with verbose logging
#   .\run-mcp-claude.ps1                           -- mock mode (simulated responses, no SolidWorks)
#
# WARNING: Without --real the server runs in MOCK MODE.  Every tool call returns simulated
#          data (blank images, nonsense mass properties).  Nothing touches SolidWorks at all.
#
# PREREQUISITE: Open SolidWorks BEFORE restarting the server.  The adapter connects to an
#               already-running SLDWORKS.exe at startup and will not launch it for you.
#
# mcp.json example (Claude Code / VS Code):
#   "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\\deployment\\run-mcp-claude.ps1",
#            "--real", "--year", "2026"]
$ErrorActionPreference = "Stop"

# This script lives in deployment/; the repo root (venv, src/) is one level up.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$startServerScript = Join-Path $repoRoot "src\utils\start_local_server_claude.py"

function Test-PythonExecutable {
	param(
		[string]$PythonPath
	)

	if (-not (Test-Path $PythonPath)) {
		return $false
	}

	# Start-Process bypasses PowerShell's own pipeline/redirection engine
	# (`| Out-Null`, `*>$null`, `2>&1`, etc). Those have been observed to
	# misbehave for native-command invocation when there is no real console
	# attached to the host process - exactly the case when an MCP client
	# spawns this script over raw stdio pipes with no pty. Piping throws
	# "Cannot run a document in the middle of a pipeline"; even stream
	# redirection has been observed to silently leave $LASTEXITCODE unset
	# instead. Start-Process goes straight to Win32 CreateProcess and has
	# neither problem.
	$stdoutFile = $null
	$stderrFile = $null
	try {
		$stdoutFile = [System.IO.Path]::GetTempFileName()
		$stderrFile = [System.IO.Path]::GetTempFileName()
		# The -c payload is quoted explicitly so Windows' command-line
		# parser keeps "import sys" as one argument instead of splitting it
		# into two.
		$proc = Start-Process -FilePath $PythonPath -ArgumentList @('-c', '"import sys"') `
			-NoNewWindow -Wait -PassThru `
			-RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
		return $proc.ExitCode -eq 0
	}
	catch {
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
		(Join-Path $repoRoot ".venv\Scripts\uv.exe")
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

if (-not (Test-Path $startServerScript)) {
	Write-Error "Start server script not found: $startServerScript"
	exit 1
}

if (Test-PythonExecutable $venvPython) {
	& $venvPython $startServerScript @args
	exit $LASTEXITCODE
}

$uvExecutable = Get-UvExecutable
if ($uvExecutable) {
	& $uvExecutable run --project $repoRoot python $startServerScript @args
	exit $LASTEXITCODE
}

Write-Error "No usable Python runtime found. Checked $venvPython and uv. Recreate the environment with 'uv venv' and reinstall dependencies if needed."
exit 1
