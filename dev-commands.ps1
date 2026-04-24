# SolidWorks MCP Python - Development Commands for PowerShell (Windows 11)
# Run individual commands: .\dev-commands.ps1 dev-test
# Or source and call directly: . .\dev-commands.ps1; dev-test

param(
    [string]$Command = ""
)

Write-Host "SolidWorks MCP Development Commands" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

function Get-VenvPython {
    return (Join-Path $PSScriptRoot ".venv\Scripts\python.exe")
}

function Ensure-Venv {
    $venvDir = Join-Path $PSScriptRoot ".venv"
    $venvCfg = Join-Path $venvDir "pyvenv.cfg"
    $venvPy  = Get-VenvPython

    # Validate existing venv
    if ((Test-Path $venvPy) -and (Test-Path $venvCfg)) {
        & $venvPy -c "import sys, unicodedata; print(sys.version_info.major)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            & $venvPy -m pip --version 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $true }
            Write-Host "Bootstrapping pip in existing .venv..." -ForegroundColor Yellow
            & $venvPy -m ensurepip --upgrade
            & $venvPy -m pip --version 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $true }
        }
        Write-Host ".venv is broken; recreating..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $venvDir -ErrorAction SilentlyContinue
    }

    # Create with uv (preferred)
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host "Creating .venv with uv..." -ForegroundColor Cyan
        uv venv .venv --python 3.11
        if ($LASTEXITCODE -eq 0 -and (Test-Path $venvPy)) {
            & $venvPy -m ensurepip --upgrade
            return $true
        }
    }

    # Fallback: py launcher or python
    $pyCmd  = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
    $pyArgs = if ($pyCmd -eq "py") { @("-3.11") } else { @() }
    Write-Host "Creating .venv with $pyCmd..." -ForegroundColor Cyan
    & $pyCmd @pyArgs -m venv .venv
    if ($LASTEXITCODE -eq 0 -and (Test-Path $venvPy)) {
        & $venvPy -m ensurepip --upgrade
        & $venvPy -m pip install --upgrade pip setuptools wheel | Out-Null
        return $true
    }

    Write-Host "ERROR: Failed to create .venv. Install uv: https://docs.astral.sh/uv/" -ForegroundColor Red
    return $false
}

function Invoke-Venv {
    param([Parameter(Mandatory = $true)][string[]]$Args)
    $venvPy = Get-VenvPython
    if (-not (Test-Path $venvPy)) {
        Write-Host "ERROR: .venv not found. Run: .\dev-commands.ps1 dev-install" -ForegroundColor Red
        $global:LASTEXITCODE = 1
        return
    }
    & $venvPy @Args
}

function Invoke-Pytest {
    param([Parameter(Mandatory = $true)][string[]]$Args)
    Invoke-Venv -Args (@("-m", "pytest") + $Args)
}

function Invoke-IntegrationCleanup {
    Invoke-Venv @("tests/scripts/cleanup_generated_integration_artifacts.py")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Generated-artifact cleanup failed (non-blocking)." -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

function dev-help {
    Write-Host "Available Commands:" -ForegroundColor Green
    Write-Host ""
    Write-Host "  dev-install         Install/sync dependencies via uv (creates/repairs .venv)"
    Write-Host "  dev-install-ui      Install/repair UI extras in .venv only"
    Write-Host "  dev-test            Run test suite with coverage (excludes solidworks_only)"
    Write-Host "  dev-test-full       Run full suite including real SolidWorks integration tests"
    Write-Host "  dev-lint            Format + lint code (ruff format + ruff check)"
    Write-Host "  dev-build           Build package for distribution"
    Write-Host "  dev-run             Start the MCP server"
    Write-Host "  dev-ui              Start FastAPI backend + Prefab dashboard"
    Write-Host "  dev-ui-probe        Start FastAPI backend + Prefab probe target"
    Write-Host "  dev-docs            Build and serve documentation (http://localhost:8000)"
    Write-Host "  dev-docs-discovery  Index SolidWorks COM/VBA documentation (Windows + SW running)"
    Write-Host "  dev-clean           Remove build/cache artifacts"
    Write-Host ""
}

function dev-install {
    Write-Host "Installing SolidWorks MCP Server..." -ForegroundColor Cyan

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: uv is required. Install from: https://docs.astral.sh/uv/" -ForegroundColor Red
        return
    }

    $ready = Ensure-Venv
    if (-not $ready) { return }

    $venvPy = Get-VenvPython
    uv pip install --python $venvPy -e ".[dev,test,docs,ui]"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Installation complete!" -ForegroundColor Green
    } else {
        Write-Host "Installation failed." -ForegroundColor Red
    }
}

function dev-install-ui {
    Write-Host "Installing/repairing UI extras in .venv..." -ForegroundColor Cyan
    $ready = Ensure-Venv
    if (-not $ready) { return }

    $venvPy = Get-VenvPython
    & $venvPy -m pip install "prefab-ui>=0.19.0" "fastapi>=0.115.0" "uvicorn>=0.24.0" -q
    if ($LASTEXITCODE -eq 0) {
        Write-Host "UI extras installed." -ForegroundColor Green
    } else {
        Write-Host "Failed to install UI extras." -ForegroundColor Red
    }
}

function dev-test {
    Write-Host "Running tests with coverage..." -ForegroundColor Cyan
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"

    # Keep generated integration artifacts from previous runs from accumulating.
    Invoke-IntegrationCleanup

    Invoke-Pytest @(
        "tests/",
        "-m", "not solidworks_only and not smoke",
        "-n", "auto",
        "--cov=src/solidworks_mcp",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml",
        "--durations=10",
        "-v"
    )

    Invoke-IntegrationCleanup

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Tests passed! Coverage: htmlcov/index.html" -ForegroundColor Green
    } else {
        Write-Host "Tests failed." -ForegroundColor Red
    }
}

function dev-test-full {
    Write-Host "Running full test suite (including real SolidWorks integration)..." -ForegroundColor Cyan
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
    $env:SOLIDWORKS_MCP_RUN_REAL_INTEGRATION = "true"

    # Generate tool catalog
    Invoke-Venv @("src/utils/generate_tool_catalog.py", "--json-only")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Tool catalog generation failed; aborting." -ForegroundColor Red
        return
    }

    # Prepare harness report stubs
    $integrationDir = Join-Path $PSScriptRoot "tests/.generated/solidworks_integration"
    if (-not (Test-Path $integrationDir)) {
        New-Item -ItemType Directory -Path $integrationDir -Force | Out-Null
    }
    $smokeReport  = Join-Path $integrationDir "smoke_test_report.json"
    $compatReport = Join-Path $integrationDir "api_compat_report.json"
    if (-not (Test-Path $smokeReport))  { "[]" | Set-Content -Path $smokeReport  -Encoding UTF8 }
    if (-not (Test-Path $compatReport)) {
        '{"solidworks_version":"unknown","required_com_interfaces":[],"discovery_status":"not_run","classification":{}}' |
            Set-Content -Path $compatReport -Encoding UTF8
    }

    # Keep live SolidWorks smoke checks serial to avoid overloading COM/SolidWorks.
    Invoke-Pytest @("tests/test_all_endpoints_harness.py", "-k", "test_smoke_all_tools", "-n", "1", "--no-cov", "-q")
    if ($LASTEXITCODE -ne 0) { Write-Host "Smoke harness failed; aborting." -ForegroundColor Red; return }

    Invoke-Pytest @("tests/test_all_endpoints_harness.py", "-k", "test_c10_docs_discovery_and_compat", "-n", "1", "--no-cov", "-q")

    # Resolve GitHub token for smoke tests
    if (-not $env:GITHUB_API_KEY -and -not $env:GH_TOKEN) {
        try {
            $ghToken = (gh auth token 2>$null).Trim()
            if ($ghToken) { $env:GITHUB_API_KEY = $ghToken }
        } catch { }
    }

    # Run non-SolidWorks/non-smoke suite in parallel to speed up the bulk of tests.
    Invoke-Pytest @(
        "tests/",
        "-m", "not solidworks_only and not smoke",
        "-n", "auto",
        "--cov=src/solidworks_mcp",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml",
        "--durations=10",
        "-v"
    )
    if ($LASTEXITCODE -ne 0) {
        Invoke-IntegrationCleanup
        Write-Host "Full tests failed in parallel subset." -ForegroundColor Red
        return
    }

    # Run live SolidWorks + smoke tests serially for stability and hardware safety.
    Invoke-Pytest @(
        "tests/",
        "-m", "solidworks_only or smoke",
        "-k", "not test_smoke_all_tools and not test_c10_docs_discovery_and_compat",
        "-n", "1",
        "--no-cov",
        "-v"
    )
    Invoke-IntegrationCleanup

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Full tests passed!" -ForegroundColor Green
    } else {
        Write-Host "Full tests failed." -ForegroundColor Red
    }
}

function dev-lint {
    Write-Host "Formatting and linting..." -ForegroundColor Cyan
    Invoke-Venv @("-m", "ruff", "format", "src/", "tests/")
    if ($LASTEXITCODE -ne 0) { Write-Host "Formatting failed." -ForegroundColor Red; return }

    Invoke-Venv @("-m", "ruff", "check", "src/", "tests/")
    if ($LASTEXITCODE -eq 0) { Write-Host "Format + lint passed!" -ForegroundColor Green }
    else { Write-Host "Lint issues found." -ForegroundColor Yellow }
}

function dev-build {
    Write-Host "Building package..." -ForegroundColor Cyan
    Invoke-Venv @("-m", "build")
    if ($LASTEXITCODE -eq 0) { Write-Host "Build complete! dist/" -ForegroundColor Green }
    else { Write-Host "Build failed." -ForegroundColor Red }
}

function dev-run {
    Write-Host "Starting MCP server..." -ForegroundColor Cyan
    Invoke-Venv @("-m", "solidworks_mcp.server")
}

function dev-ui {
    Write-Host "Starting UI (FastAPI + Prefab dashboard)..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "run-ui.ps1") -FrontendTarget "src/solidworks_mcp/ui/prefab_dashboard.py"
}

function dev-ui-probe {
    Write-Host "Starting UI probe (FastAPI + Prefab probe)..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "run-ui.ps1") -FrontendTarget "src/solidworks_mcp/ui/prefab_trace_probe.py"
}

function dev-docs {
    Write-Host "Building docs..." -ForegroundColor Cyan
    Invoke-Venv @("-m", "mkdocs", "build", "--clean")
    if ($LASTEXITCODE -ne 0) { Write-Host "Docs build failed." -ForegroundColor Red; return }
    Write-Host "Serving at http://localhost:8000 (Ctrl+C to stop)..." -ForegroundColor Yellow
    Invoke-Venv @("-m", "mkdocs", "serve", "--dev-addr=localhost:8000")
}

function dev-docs-discovery {
    Write-Host "Indexing SolidWorks COM and VBA documentation..." -ForegroundColor Cyan
    # $IsWindows and PSVersionTable.Platform only exist in PS 6+; PS 5.1 is Windows-exclusive so treat missing Platform as Windows
    $isWindowsOS = $IsWindows -or ($PSVersionTable.Platform -eq "Win32NT") -or ($null -eq $PSVersionTable.Platform)
    if (-not $isWindowsOS) {
        Write-Host "ERROR: Windows only." -ForegroundColor Red
        return
    }
    $swProcess = Get-Process | Where-Object { $_.ProcessName -like "*sldworks*" }
    if (-not $swProcess) {
        Write-Host "WARNING: SolidWorks not running. Start it and retry." -ForegroundColor Yellow
        return
    }
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
    $repoRoot = $PSScriptRoot.Replace("'", "''")
    $pythonCode = @"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(r'$repoRoot') / 'src'))
from solidworks_mcp.tools.docs_discovery import SolidWorksDocsDiscovery
d = SolidWorksDocsDiscovery()
d.discover_all()
f = d.save_index()
s = d.create_search_summary()
print('COM Objects:', s.get('total_com_objects'), ' Methods:', s.get('total_methods'), ' Index:', f)
"@
    Invoke-Venv -Args @("-c", $pythonCode)
    if ($LASTEXITCODE -eq 0) { Write-Host "Discovery complete." -ForegroundColor Green }
    else { Write-Host "Discovery failed." -ForegroundColor Red }
}

function dev-clean {
    Write-Host "Cleaning build artifacts..." -ForegroundColor Cyan
    @("build", "dist", "htmlcov", ".pytest_cache", ".mypy_cache", "site", "*.egg-info") | ForEach-Object {
        Get-ChildItem -Path . -Filter $_ -Recurse -Directory -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -Path .coverage, coverage.xml -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Filter "*.egg-info" -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Filter "__pycache__"  -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Filter "*.pyc"         -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "Clean complete!" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

if ([string]::IsNullOrWhiteSpace($Command) -or $Command -eq "dev-help") {
    dev-help
} elseif (Get-Command -Name $Command -CommandType Function -ErrorAction SilentlyContinue) {
    & $Command
} else {
    Write-Host "Unknown command: $Command" -ForegroundColor Red
    dev-help
    exit 1
}
