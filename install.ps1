<#
.SYNOPSIS
    Install the SolidWorks MCP server into .venv and connect your MCP clients.

.DESCRIPTION
    1. Finds Python 3.13 or newer (the py launcher first, then python on the PATH).
    2. Creates .venv beside this script, if it doesn't exist.
    3. Installs this project into it (with uv if it's on the PATH, else pip).
    4. Runs `solidworks-mcp setup`, which finds SolidWorks and your MCP clients
       and adds the server to the ones you choose.

    Any arguments are passed to `solidworks-mcp setup`, for example:
        .\install.ps1 --dry-run
        .\install.ps1 --client claude-desktop --yes

.NOTES
    If scripts are blocked, run it once with:
        powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Find-Python {
    # The py launcher can pick a version even when python on the PATH is older.
    $candidates = @(
        @{ Exe = "py"; Args = @("-3.13") },
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() }
    )
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
        $version = & $candidate.Exe @($candidate.Args) -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and [version]$version -ge [version]"3.13") {
            return $candidate
        }
    }
    throw "Python 3.13 or newer was not found. Install it from https://www.python.org/downloads/ and run this script again."
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $python = Find-Python
    Write-Host "Creating .venv with $($python.Exe) $($python.Args)..."
    & $python.Exe @($python.Args) -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Creating .venv failed." }
}

$venvDir = Join-Path $PSScriptRoot ".venv"
$launcher = Join-Path $venvDir "Scripts\solidworks-mcp.exe"

function Get-VenvProcesses {
    # Programs running from .venv, e.g. the server an MCP client started.
    # Windows locks a running .exe, so an install that replaces it fails
    # partway and leaves packages half-removed.
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($venvDir, [StringComparison]::OrdinalIgnoreCase) }
}

$running = @(Get-VenvProcesses)
$installed = $false
if (Test-Path $launcher) {
    & $venvPython -c "import solidworks_mcp" 2>$null
    $installed = $LASTEXITCODE -eq 0
}

if ($running -and $installed) {
    # The install is editable, so code changes are already live; only a
    # dependency change needs a reinstall, and that has to wait.
    $names = ($running | ForEach-Object { "$($_.ProcessName) ($($_.Id))" }) -join ", "
    Write-Host "The server is already installed and running ($names), so the install step is skipped."
    Write-Host "To update dependencies, quit your MCP clients (e.g. Claude Desktop from the tray) and run this script again."
} elseif ($running) {
    $names = ($running | ForEach-Object { "$($_.ProcessName) ($($_.Id))" }) -join ", "
    throw "Programs are running from .venv ($names). Quit them (your MCP clients start them) and run this script again."
} else {
    Write-Host "Installing the SolidWorks MCP server into .venv..."
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        # uv is faster, and pip can't upgrade packages that uv installed.
        uv pip install --quiet --python $venvPython -e .
    } else {
        & $venvPython -m pip install --quiet --upgrade pip
        & $venvPython -m pip install --quiet -e .
    }
    if ($LASTEXITCODE -ne 0) { throw "Installing the package failed; see the output above." }
}

# Hand over to the guided setup; it asks before changing any client config.
& $launcher setup @args
exit $LASTEXITCODE
