# PowerShell script to run the FastAPI UI backend and Prefab dashboard frontend.
# Similar to run-mcp.ps1, this script provides a single entry point for local UI startup.
#
# Usage:
#   .\run-ui.ps1
#   .\run-ui.ps1 -BackendPort 8766 -FrontendPort 5175
#   .\run-ui.ps1 -Probe
#   .\run-ui.ps1 -NoNewWindows
#   .\run-ui.ps1 -DryRun

param(
    [int]$BackendPort = 8766,
    [int]$FrontendPort = 5175,
    [string]$FrontendTarget = "src/solidworks_mcp/ui/prefab_dashboard.py",
    [switch]$Probe,
    [switch]$NoNewWindows,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcPath = Join-Path $scriptDir "src"
$probeTarget = "src/solidworks_mcp/ui/prefab_trace_probe.py"
$uiLogDir = Join-Path $scriptDir ".solidworks_mcp\ui_logs"
$backendLog = Join-Path $uiLogDir "fastapi_server.log"
$frontendLog = Join-Path $uiLogDir "prefab_ui.log"

function Get-PortOwners {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        return @()
    }

    $owners = @()
    foreach ($connection in ($connections | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $process = Get-Process -Id $connection -ErrorAction SilentlyContinue
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $connection" -ErrorAction SilentlyContinue
        $owners += [PSCustomObject]@{
            Port = $Port
            Pid = $connection
            Name = if ($process) { $process.ProcessName } else { "<unknown>" }
            Path = if ($process) { $process.Path } else { $null }
            CommandLine = if ($cim) { $cim.CommandLine } else { $null }
        }
    }

    return $owners
}

function Test-IsRepoUiProcess {
    param([object]$Owner)

    $commandLine = [string]($Owner.CommandLine)
    $path = [string]($Owner.Path)
    $name = [string]($Owner.Name)

    if ([string]::IsNullOrWhiteSpace($commandLine) -and [string]::IsNullOrWhiteSpace($path)) {
        return $true
    }

    if ($name -in @("python", "pythonw", "pwsh", "powershell", "<unknown>")) {
        return $true
    }

    $repoHints = @(
        $scriptDir,
        "solidworks_mcp.ui.server:app",
        "prefab_ui.cli",
        "prefab.exe",
        "run-ui.ps1"
    )

    foreach ($hint in $repoHints) {
        if ($commandLine -like "*$hint*" -or $path -like "*$hint*") {
            return $true
        }
    }

    return $false
}

function Resolve-UiPorts {
    param([int[]]$Ports)

    foreach ($port in $Ports) {
        $owners = @(Get-PortOwners -Port $port)
        if (-not $owners.Count) {
            continue
        }

        $foreignOwners = @($owners | Where-Object { -not (Test-IsRepoUiProcess $_) })
        if ($foreignOwners.Count) {
            $details = $foreignOwners | ForEach-Object {
                "PID=$($_.Pid) Name=$($_.Name) Command=$($_.CommandLine)"
            }
            Write-Error (
                "Port $port is already in use by a non-dashboard process.`n" +
                ($details -join "`n") +
                "`nStop that process or launch with a different port."
            )
            exit 1
        }

        foreach ($owner in $owners) {
            try {
                Stop-Process -Id $owner.Pid -Force -ErrorAction Stop
                Write-Host "Stopped stale UI process on port $port (PID $($owner.Pid), $($owner.Name))." -ForegroundColor Yellow
            } catch {
                if ($_.Exception.Message -like "*Cannot find a process with the process identifier*") {
                    Write-Host "Stale UI process PID $($owner.Pid) on port $port had already exited." -ForegroundColor Yellow
                    continue
                }
                Write-Error "Failed to stop stale UI process PID $($owner.Pid) on port ${port}: $_"
                exit 1
            }
        }
    }
}

if (-not (Test-Path $uiLogDir)) {
    New-Item -ItemType Directory -Path $uiLogDir -Force | Out-Null
}

if ($Probe) {
    $FrontendTarget = $probeTarget
}

if ([string]::IsNullOrWhiteSpace($FrontendTarget)) {
    Write-Error "FrontendTarget cannot be empty. Use -Probe for the trace app or pass a valid file path."
    exit 1
}

$resolvedFrontendTarget = Join-Path $scriptDir $FrontendTarget
if (-not (Test-Path $resolvedFrontendTarget)) {
    Write-Error "Frontend target not found: $FrontendTarget"
    exit 1
}

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
$venvPrefab = Join-Path $scriptDir ".venv\Scripts\prefab.exe"

if (-not (Test-Path $venvPython)) {
    Write-Error (
        "Virtual environment python not found: $venvPython`n" +
        "Run one of:`n" +
        "  .\dev-commands.ps1 dev-install`n" +
        "  .\dev-commands.ps1 dev-install-uv"
    )
    exit 1
}

$pipCheck = & $venvPython -m pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip missing in .venv - bootstrapping with ensurepip..." -ForegroundColor Yellow
    & $venvPython -m ensurepip --upgrade
}

Resolve-UiPorts -Ports @($BackendPort, $FrontendPort)

# If prefab.exe is missing, try to install prefab-ui then re-check.
# This handles fresh installs where pip may not have written the console script.
if (-not (Test-Path $venvPrefab)) {
    Write-Host "prefab.exe not found - installing/repairing prefab-ui..." -ForegroundColor Yellow
    & $venvPython -m pip install --quiet --force-reinstall "prefab-ui>=0.19.0"
    if (-not (Test-Path $venvPrefab)) {
        # Final fallback: invoke via python -m prefab_ui.cli (no .exe needed)
        Write-Host "prefab.exe still missing; falling back to 'python -m prefab_ui.cli'." -ForegroundColor Yellow
        $venvPrefab = $null  # signal to use module path
    }
}

# Build command strings for the two processes
$backendCmd = "`"$venvPython`" -m uvicorn solidworks_mcp.ui.server:app --host 127.0.0.1 --port $BackendPort --reload --reload-dir src"
$backendShellCommand = "Set-Location -LiteralPath '$scriptDir'; `$env:PYTHONPATH='$srcPath'; & '$venvPython' -m uvicorn solidworks_mcp.ui.server:app --host 127.0.0.1 --port $BackendPort --reload --reload-dir src 2>&1 | Tee-Object -FilePath '$backendLog' -Append"

if ($venvPrefab) {
    $frontendCmd = "`"$venvPrefab`" serve $FrontendTarget --port $FrontendPort --reload"
    $frontendShellCommand = "Set-Location -LiteralPath '$scriptDir'; `$env:SOLIDWORKS_UI_API_ORIGIN='http://127.0.0.1:$BackendPort'; `$env:PYTHONUTF8='1'; & '$venvPrefab' serve $FrontendTarget --port $FrontendPort --reload 2>&1 | Tee-Object -FilePath '$frontendLog' -Append"
} else {
    $frontendCmd = "`"$venvPython`" -m prefab_ui.cli serve $FrontendTarget --port $FrontendPort --reload"
    $frontendShellCommand = "Set-Location -LiteralPath '$scriptDir'; `$env:SOLIDWORKS_UI_API_ORIGIN='http://127.0.0.1:$BackendPort'; `$env:PYTHONUTF8='1'; & '$venvPython' -m prefab_ui.cli serve $FrontendTarget --port $FrontendPort --reload 2>&1 | Tee-Object -FilePath '$frontendLog' -Append"
}

$backendArgs = @(
    "-m",
    "uvicorn",
    "solidworks_mcp.ui.server:app",
    "--host",
    "127.0.0.1",
    "--port",
    "$BackendPort",
    "--reload",
    "--reload-dir",
    "src"
)

# Build frontend args depending on whether prefab.exe exists
if ($venvPrefab) {
    $frontendExe = $venvPrefab
    $frontendArgs = @(
        "serve",
        $FrontendTarget,
        "--port",
        "$FrontendPort",
        "--reload"
    )
} else {
    $frontendExe = $venvPython
    $frontendArgs = @(
        "-m",
        "prefab_ui.cli",
        "serve",
        $FrontendTarget,
        "--port",
        "$FrontendPort",
        "--reload"
    )
}

Write-Host "Starting SolidWorks UI stack" -ForegroundColor Cyan
Write-Host "- Backend : http://127.0.0.1:$BackendPort" -ForegroundColor Yellow
Write-Host "- OpenAPI : http://127.0.0.1:$BackendPort/docs" -ForegroundColor Yellow
Write-Host "- Frontend: http://127.0.0.1:$FrontendPort" -ForegroundColor Yellow
Write-Host "- Target  : $FrontendTarget" -ForegroundColor Yellow
Write-Host "- Logs    : $uiLogDir" -ForegroundColor Yellow
Write-Host "  - FastAPI/Uvicorn: $backendLog" -ForegroundColor Yellow
Write-Host "  - Prefab UI      : $frontendLog" -ForegroundColor Yellow
Write-Host ""

if ($DryRun) {
    Write-Host "Dry run enabled. Commands:" -ForegroundColor Green
    Write-Host "Backend : $backendCmd"
    Write-Host "Frontend: $frontendCmd"
    exit 0
}

if ($NoNewWindows) {
    Write-Host "Running backend and frontend in background jobs in this shell..." -ForegroundColor Cyan

    Start-Job -Name "solidworks-ui-backend" -ScriptBlock {
        param($workingDir, $pythonExe, $argsArray, $pythonPath, $backendLogPath)
        Set-Location $workingDir
        $env:PYTHONPATH = $pythonPath
        & $pythonExe @argsArray *>> $backendLogPath
    } -ArgumentList $scriptDir, $venvPython, $backendArgs, $srcPath, $backendLog | Out-Null

    Start-Job -Name "solidworks-ui-frontend" -ScriptBlock {
        param($workingDir, $prefabExe, $argsArray, $apiOrigin, $frontendLogPath)
        Set-Location $workingDir
        $env:SOLIDWORKS_UI_API_ORIGIN = $apiOrigin
        $env:PYTHONUTF8 = "1"
        & $prefabExe @argsArray *>> $frontendLogPath
    } -ArgumentList $scriptDir, $frontendExe, $frontendArgs, "http://127.0.0.1:$BackendPort", $frontendLog | Out-Null

    Write-Host "Started jobs: solidworks-ui-backend, solidworks-ui-frontend" -ForegroundColor Green
    Write-Host "Use Get-Job / Receive-Job / Stop-Job to monitor and stop." -ForegroundColor Yellow
    exit 0
}

Write-Host "Launching two PowerShell windows..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $backendShellCommand
)
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $frontendShellCommand
)

Write-Host "UI stack launch requested." -ForegroundColor Green
