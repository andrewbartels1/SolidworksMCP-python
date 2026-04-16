# SolidWorks MCP Python - Development Commands for PowerShell (Windows 11)
# Run individual functions or source this script and call them as needed
# Example: . .\dev-commands.ps1; dev-test

param(
    [string]$Command = ""
)

Write-Host "SolidWorks MCP Development Commands" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Helper function to check if environment exists
function Test-MicromambaEnv {
    try {
        $envList = micromamba env list --json | ConvertFrom-Json
        return ($envList.envs | Where-Object { $_ -match "[/\\]solidworks_mcp$" }).Count -gt 0
    } catch {
        return $false
    }
}

function Invoke-ProjectPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    $micromambaCmd = Get-Command micromamba -ErrorAction SilentlyContinue
    if ($micromambaCmd -and (Test-MicromambaEnv)) {
        micromamba run -n solidworks_mcp python @Args
        return
    }

    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        # Validate the venv is functional and meets the minimum Python version (>=3.11).
        $venvMinor = & $venvPython -c "import sys; print(sys.version_info.minor if sys.version_info.major==3 else 0)" 2>$null
        $venvMajor = & $venvPython -c "import sys; print(sys.version_info.major)" 2>$null
        if ($LASTEXITCODE -eq 0 -and [int]$venvMajor -eq 3 -and [int]$venvMinor -ge 11) {
            & $venvPython @Args
            return
        }
        Write-Host ""
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: .venv Python is broken (its base interpreter is missing)." -ForegroundColor Red
            Write-Host "The Python version used to create .venv was uninstalled from this machine." -ForegroundColor Yellow
        } else {
            Write-Host "ERROR: .venv Python is 3.$venvMinor but this project requires Python >=3.11." -ForegroundColor Red
            Write-Host "The .venv was created with an incompatible Python version." -ForegroundColor Yellow
        }
        Write-Host "Recreate the venv with Python 3.11+:" -ForegroundColor Yellow
        Write-Host "  Remove-Item -Recurse -Force .venv" -ForegroundColor Cyan
        Write-Host "  py -3.11 -m venv .venv   # or: python3.11 -m venv .venv" -ForegroundColor Cyan
        Write-Host "  .\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel" -ForegroundColor Cyan
        Write-Host "  .\.venv\Scripts\python.exe -m pip install -e `".[dev,test,docs]`"" -ForegroundColor Cyan
        Write-Host ""
        $global:LASTEXITCODE = 1
        return
    }

    throw "No Python runtime found. Install micromamba or create .venv first."
}

function Invoke-ProjectPytest {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    $pytestArgs = @("-m", "pytest")

    $pluginAutoloadDisabled = if ($env:PYTEST_DISABLE_PLUGIN_AUTOLOAD) { $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD.Trim().ToLowerInvariant() } else { "" }
    if ($pluginAutoloadDisabled -in @("1", "true", "yes", "on")) {
        $pytestArgs += @(
            "-p", "pytest_asyncio.plugin",
            "-p", "pytest_cov"
        )
    }

    $pytestArgs += $Args

    Invoke-ProjectPython -Args $pytestArgs
}

function dev-help {
    Write-Host "Available Commands:" -ForegroundColor Green
    Write-Host ""
    Write-Host "dev-install           - Install dependencies and setup environment"
    Write-Host "dev-install-ui        - Install/repair UI extras (prefab-ui, fastapi) in .venv"
    Write-Host "dev-test              - Run test suite with coverage"
    Write-Host "dev-test-context-budget - Run smoke response-size guard test"
    Write-Host "dev-generate-tool-catalog - Generate tests/.generated/tool_catalog.json"
    Write-Host "dev-prepare-harness-reports - Generate harness smoke/compat report artifacts"
    Write-Host "dev-test-full         - Run full suite including real SolidWorks integration tests"
    Write-Host "dev-test-clean        - Remove generated integration test artifacts"
    Write-Host "dev-docs              - Serve documentation locally (http://localhost:8000)"
    Write-Host "dev-make-docs-build   - Build docs locally (supports -Quiet when sourced)"
    Write-Host "dev-make-docs-serve   - Build-check docs then serve locally (http://localhost:8000)"
    Write-Host "dev-docs-discovery    - Index SolidWorks COM/VBA documentation (Windows-only)"
    Write-Host "dev-build             - Build package for distribution"
    Write-Host "dev-run               - Start the MCP server"
    Write-Host "dev-ui                - Start FastAPI backend + Prefab dashboard launcher"
    Write-Host "dev-ui-probe          - Start FastAPI backend + minimal Prefab probe app"
    Write-Host "dev-clean             - Clean build artifacts"
    Write-Host "dev-lint              - Run code linting (ruff)"
    Write-Host "dev-format            - Format code (ruff)"
    Write-Host ""
}

function Invoke-ProjectModule {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    $micromambaCmd = Get-Command micromamba -ErrorAction SilentlyContinue
    if ($micromambaCmd -and (Test-MicromambaEnv)) {
        micromamba run -n solidworks_mcp @Args
        return
    }

    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        # Validate the venv is functional and meets the minimum Python version (>=3.11).
        $venvMinor = & $venvPython -c "import sys; print(sys.version_info.minor if sys.version_info.major==3 else 0)" 2>$null
        $venvMajor = & $venvPython -c "import sys; print(sys.version_info.major)" 2>$null
        if ($LASTEXITCODE -eq 0 -and [int]$venvMajor -eq 3 -and [int]$venvMinor -ge 11) {
            & $venvPython @Args
            return
        }
        Write-Host ""
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: .venv Python is broken (its base interpreter is missing)." -ForegroundColor Red
            Write-Host "The Python version used to create .venv was uninstalled from this machine." -ForegroundColor Yellow
        } else {
            Write-Host "ERROR: .venv Python is 3.$venvMinor but this project requires Python >=3.11." -ForegroundColor Red
            Write-Host "The .venv was created with an incompatible Python version." -ForegroundColor Yellow
        }
        Write-Host "Recreate the venv with Python 3.11+:" -ForegroundColor Yellow
        Write-Host "  Remove-Item -Recurse -Force .venv" -ForegroundColor Cyan
        Write-Host "  py -3.11 -m venv .venv   # or: python3.11 -m venv .venv" -ForegroundColor Cyan
        Write-Host "  .\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel" -ForegroundColor Cyan
        Write-Host "  .\.venv\Scripts\python.exe -m pip install -e `".[dev,test,docs]`"" -ForegroundColor Cyan
        Write-Host ""
        $global:LASTEXITCODE = 1
        return
    }

    throw "No Python runtime found. Install micromamba or create .venv first."
}

function dev-install {
    Write-Host "Installing SolidWorks MCP Server..." -ForegroundColor Cyan

    if (-not (Get-Command micromamba -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "ERROR: 'micromamba' is not installed or not on PATH." -ForegroundColor Red
        Write-Host ""
        Write-Host "Install micromamba for Windows PowerShell by running:" -ForegroundColor Yellow
        Write-Host "  Invoke-Expression ((Invoke-WebRequest -Uri https://micro.mamba.pm/install.ps1 -UseBasicParsing).Content)" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "After installation, open a new PowerShell window and retry:" -ForegroundColor Yellow
        Write-Host "  .\dev-commands.ps1 dev-install" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Alternatively, use the virtualenv path (no micromamba required):" -ForegroundColor Yellow
        Write-Host "  python -m venv .venv" -ForegroundColor Cyan
        Write-Host "  .\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel" -ForegroundColor Cyan
        Write-Host "  .\.venv\Scripts\python.exe -m pip install -e `".[dev,test,docs,ui]`"" -ForegroundColor Cyan
        Write-Host ""
        return
    }

    micromamba env create -f solidworks_mcp.yml --yes
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Installing Python package in development mode (all extras incl. ui)..." -ForegroundColor Cyan
        micromamba run -n solidworks_mcp pip install -e ".[dev,test,docs,ui]"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Syncing .venv from micromamba Python for run-ui.ps1 compatibility..." -ForegroundColor Cyan
            $mmPython = micromamba run -n solidworks_mcp python -c "import sys; print(sys.executable)" 2>&1
            if (Test-Path ".venv") {
                if (-not (Test-Path ".venv\pyvenv.cfg")) {
                    Write-Host "Recreating broken .venv..." -ForegroundColor Yellow
                    try { Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue } catch {}
                }
            }
            if (-not (Test-Path ".venv")) {
                & $mmPython -m venv .venv
            }
            if (Test-Path ".venv\pyvenv.cfg") {
                $venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
                $pipCheck = & $venvPy -m pip --version 2>&1
                if ($LASTEXITCODE -ne 0) { & $venvPy -m ensurepip --upgrade }
                & $venvPy -m pip install "prefab-ui>=0.19.0" "fastapi>=0.115.0" "uvicorn>=0.24.0" -q
                Write-Host ".venv synced with UI extras." -ForegroundColor Green
            }
            Write-Host "Installation complete!" -ForegroundColor Green
        } else {
            Write-Host "Failed to install Python package" -ForegroundColor Red
        }
    } else {
        Write-Host "Failed to create conda environment" -ForegroundColor Red
    }
}

function dev-install-ui {
    Write-Host "Installing/repairing UI extras (prefab-ui, fastapi) in .venv..." -ForegroundColor Cyan
    $venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        Write-Host "ERROR: .venv not found. Run 'dev-install' first." -ForegroundColor Red
        return
    }
    if (-not (Test-Path (Join-Path $PSScriptRoot ".venv\pyvenv.cfg"))) {
        Write-Host "ERROR: .venv is corrupted (no pyvenv.cfg). Run 'dev-install' first." -ForegroundColor Red
        return
    }
    $pipCheck = & $venvPy -m pip --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Bootstrapping pip in .venv..." -ForegroundColor Yellow
        & $venvPy -m ensurepip --upgrade
    }
    & $venvPy -m pip install "prefab-ui>=0.19.0" "fastapi>=0.115.0" "uvicorn>=0.24.0" -q
    if ($LASTEXITCODE -eq 0) {
        Write-Host "UI extras installed. Test with: .\dev-commands.ps1 dev-ui-probe" -ForegroundColor Green
    } else {
        Write-Host "Failed to install UI extras." -ForegroundColor Red
    }
}

function dev-test {
    Write-Host "Running tests with coverage..." -ForegroundColor Cyan
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
    Invoke-ProjectPytest -Args @(
        "tests/",
        "-m", "not solidworks_only and not smoke",
        "--cov=src/solidworks_mcp",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml",
        "--durations=10",
        "-v"
    )
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Tests passed!" -ForegroundColor Green
        Write-Host "Coverage report: htmlcov/index.html" -ForegroundColor Yellow
    } else {
        Write-Host "Tests failed" -ForegroundColor Red
    }
}

function dev-test-context-budget {
    Write-Host "Running smoke response-size guard test..." -ForegroundColor Cyan
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
    Invoke-ProjectPytest -Args @(
        "tests/test_all_endpoints_harness.py",
        "-k", "test_smoke_responses_within_context_budget",
        "--no-cov",
        "-q"
    )
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Response-size guard passed!" -ForegroundColor Green
    } else {
        Write-Host "Response-size guard failed" -ForegroundColor Red
    }
}

function dev-generate-tool-catalog {
    Write-Host "Generating tool catalog JSON for endpoint harness tests..." -ForegroundColor Cyan
    Invoke-ProjectPython -Args @("src/utils/generate_tool_catalog.py", "--json-only")
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Tool catalog generated at tests/.generated/tool_catalog.json" -ForegroundColor Green
    } else {
        Write-Host "Failed to generate tool catalog JSON" -ForegroundColor Red
    }
}

function dev-prepare-harness-reports {
    Write-Host "Preparing endpoint harness report artifacts..." -ForegroundColor Cyan

    $integrationDir = Join-Path $PSScriptRoot "tests/.generated/solidworks_integration"
    if (-not (Test-Path $integrationDir)) {
        New-Item -ItemType Directory -Path $integrationDir -Force | Out-Null
    }

    $smokeReport = Join-Path $integrationDir "smoke_test_report.json"
    if (-not (Test-Path $smokeReport)) {
        "[]" | Set-Content -Path $smokeReport -Encoding UTF8
    }

    $compatReport = Join-Path $integrationDir "api_compat_report.json"
    if (-not (Test-Path $compatReport)) {
        @'
{
  "solidworks_version": "unknown",
  "required_com_interfaces": [],
  "discovery_status": "not_run",
  "classification": {}
}
'@ | Set-Content -Path $compatReport -Encoding UTF8
    }

    # Refresh smoke report with live data using the mock-safe Level B writer test.
    Invoke-ProjectPytest -Args @(
        "tests/test_all_endpoints_harness.py",
        "-k", "test_smoke_all_tools",
        "--no-cov",
        "-q"
    )
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to generate smoke_test_report.json" -ForegroundColor Red
        return
    }

    # Refresh compat report with live data when real integration is available.
    Invoke-ProjectPytest -Args @(
        "tests/test_all_endpoints_harness.py",
        "-k", "test_c10_docs_discovery_and_compat",
        "--no-cov",
        "-q"
    )

    if (-not (Test-Path $smokeReport) -or -not (Test-Path $compatReport)) {
        Write-Host "Harness report artifacts were not created as expected" -ForegroundColor Red
        $global:LASTEXITCODE = 1
        return
    }

    Write-Host "Harness reports ready under tests/.generated/solidworks_integration" -ForegroundColor Green
    $global:LASTEXITCODE = 0
}

function dev-test-full {
    Write-Host "Running full test suite (including real SolidWorks integration)..." -ForegroundColor Cyan
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
    $env:SOLIDWORKS_MCP_RUN_REAL_INTEGRATION = "true"

    dev-generate-tool-catalog
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Skipping test run because tool catalog generation failed" -ForegroundColor Red
        return
    }

    dev-prepare-harness-reports
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Skipping test run because harness reports could not be prepared" -ForegroundColor Red
        return
    }

    # Resolve GitHub token for smoke tests (gh auth token fallback).
    if (-not $env:GITHUB_API_KEY -and -not $env:GH_TOKEN) {
        try {
            $ghToken = (gh auth token 2>$null).Trim()
            if ($ghToken) {
                $env:GITHUB_API_KEY = $ghToken
                Write-Host "GitHub token resolved via 'gh auth token'." -ForegroundColor Green
            }
        } catch { }
    }

    # tests/ includes all suites, including the full endpoint harness tests.
    Invoke-ProjectPytest -Args @(
        "tests/",
        "--cov=src/solidworks_mcp",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml",
        "--durations=10",
        "-v"
    )
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Full tests passed!" -ForegroundColor Green
        dev-test-clean
    } else {
        Write-Host "Full tests failed" -ForegroundColor Red
    }
}

function dev-test-clean {
    Write-Host "Cleaning generated integration artifacts..." -ForegroundColor Cyan

    # Allow SolidWorks/file-system handles to settle before delete attempts.
    Start-Sleep -Seconds 2

    Invoke-ProjectPython -Args @("tests/scripts/cleanup_generated_integration_artifacts.py")
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Cleanup complete!" -ForegroundColor Green
        return
    }

    Write-Host "First cleanup attempt failed; retrying after pause..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
    Invoke-ProjectPython -Args @("tests/scripts/cleanup_generated_integration_artifacts.py")

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Cleanup complete on retry!" -ForegroundColor Green
    } else {
        Write-Host "Cleanup failed" -ForegroundColor Red
    }
}

function dev-docs {
    Write-Host "Starting documentation server..." -ForegroundColor Cyan
    Write-Host "Available at: http://localhost:8000" -ForegroundColor Yellow
    Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
    Write-Host ""
    dev-make-docs-serve
}

function dev-make-docs-build {
    param(
        [switch]$Quiet
    )

    Write-Host "Validating docs build..." -ForegroundColor Cyan

    $buildArgs = @("-m", "mkdocs", "build", "--clean")
    if ($Quiet) {
        $buildArgs += "--quiet"
    }

    Invoke-ProjectModule -Args $buildArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Docs build passed." -ForegroundColor Green
    } else {
        Write-Host "Docs build failed." -ForegroundColor Red
    }
}

function dev-make-docs-serve {
    param(
        [switch]$Quiet
    )

    dev-make-docs-build -Quiet:$Quiet

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Docs build failed; fix errors before serving." -ForegroundColor Red
        return
    }

    Write-Host "Starting documentation server..." -ForegroundColor Cyan
    Write-Host "Available at: http://localhost:8000" -ForegroundColor Yellow
    Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
    Write-Host ""

    $serveArgs = @("-m", "mkdocs", "serve", "--dev-addr=localhost:8000")
    if ($Quiet) {
        $serveArgs += "--quiet"
    }

    Invoke-ProjectModule -Args $serveArgs
}

function dev-docs-discovery {
    Write-Host "Indexing SolidWorks COM and VBA documentation..." -ForegroundColor Cyan
    Write-Host ""
    
    # Check if running on Windows
    if ($IsWindows -or $PSVersionTable.Platform -eq "Win32NT") {
        # Check if SolidWorks is running
        $swProcess = Get-Process | Where-Object { $_.ProcessName -like "*sldworks*" -or $_.ProcessName -like "*SLDWORKS*" }
        
        if ($null -eq $swProcess) {
            Write-Host "Warning: SolidWorks does not appear to be running." -ForegroundColor Yellow
            Write-Host "Please start SolidWorks and try again." -ForegroundColor Yellow
            return
        }
        
        Write-Host "SolidWorks is running; proceeding with documentation discovery..." -ForegroundColor Green
        Write-Host ""
        
        # Run the docs discovery Python script
        $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
        Invoke-ProjectPython -Args @("-c", @"
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))

from solidworks_mcp.tools.docs_discovery import SolidWorksDocsDiscovery

try:
    discovery = SolidWorksDocsDiscovery()
    index = discovery.discover_all()
    output_file = discovery.save_index()
    summary = discovery.create_search_summary()
    
    print("\n" + "="*60)
    print("Documentation Discovery Complete!")
    print("="*60)
    print(f"COM Objects Discovered: {summary['total_com_objects']}")
    print(f"Methods Indexed: {summary['total_methods']}")
    print(f"Properties Indexed: {summary['total_properties']}")
    print(f"SolidWorks Version: {summary['solidworks_version']}")
    print(f"VBA Libraries Available: {len(summary['available_vba_libs'])}")
    if output_file:
        print(f"\nIndex saved to: {output_file}")
    print("="*60 + "\n")
    
except Exception as e:
    print(f"Error during discovery: {e}", file=sys.stderr)
    sys.exit(1)
"@)
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Documentation indexing complete!" -ForegroundColor Green
            Write-Host "Index file: .generated/docs-index/solidworks_docs_index.json" -ForegroundColor Yellow
        } else {
            Write-Host "Documentation discovery failed" -ForegroundColor Red
        }
    } else {
        Write-Host "Error: Documentation discovery only works on Windows" -ForegroundColor Red
        Write-Host "This requires COM access to SolidWorks and win32com" -ForegroundColor Yellow
    }
}

function dev-build {
    Write-Host "Building package for distribution..." -ForegroundColor Cyan
    Invoke-ProjectPython -Args @("-m", "build")
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Build complete! Package ready in dist/" -ForegroundColor Green
    } else {
        Write-Host "Build failed" -ForegroundColor Red
    }
}

function dev-run {
    Write-Host "Starting MCP server..." -ForegroundColor Cyan
    Invoke-ProjectPython -Args @("-m", "solidworks_mcp.server")
}

function dev-ui {
    Write-Host "Starting UI launcher (FastAPI + Prefab)..." -ForegroundColor Cyan
    $uiLauncher = Join-Path $PSScriptRoot "run-ui.ps1"
    if (-not (Test-Path $uiLauncher)) {
        Write-Host "UI launcher script not found: $uiLauncher" -ForegroundColor Red
        return
    }

    & $uiLauncher
}

function dev-ui-probe {
    Write-Host "Starting UI probe launcher (FastAPI + minimal Prefab probe)..." -ForegroundColor Cyan
    $uiLauncher = Join-Path $PSScriptRoot "run-ui.ps1"
    if (-not (Test-Path $uiLauncher)) {
        Write-Host "UI launcher script not found: $uiLauncher" -ForegroundColor Red
        return
    }

    & $uiLauncher -FrontendTarget "src/solidworks_mcp/ui/prefab_trace_probe.py"
}

function dev-clean {
    Write-Host "Cleaning build artifacts..." -ForegroundColor Cyan
    
    $dirs = @("build", "dist", "htmlcov", ".pytest_cache", ".mypy_cache", "site", "*.egg-info")
    foreach ($dir in $dirs) {
        Get-ChildItem -Path . -Filter $dir -Recurse -Directory -ErrorAction SilentlyContinue | 
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    Remove-Item -Path .coverage, coverage.xml -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Filter "*.egg-info" -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Filter "__pycache__" -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Filter "*.pyc" -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue
    
    Write-Host "Cleanup complete!" -ForegroundColor Green
}

function dev-lint {
    Write-Host "Running linting (ruff check)..." -ForegroundColor Cyan
    Invoke-ProjectPython -Args @("-m", "ruff", "check", "src/", "tests/")
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Linting passed!" -ForegroundColor Green
    } else {
        Write-Host "Linting issues found" -ForegroundColor Yellow
    }
}

function dev-format {
    Write-Host "Formatting code (ruff format)..." -ForegroundColor Cyan
    Invoke-ProjectPython -Args @("-m", "ruff", "format", "src/", "tests/")
    Write-Host "Formatting complete!" -ForegroundColor Green
}

# Display help on first load, or run a specific command when provided.
if ([string]::IsNullOrWhiteSpace($Command)) {
    dev-help
} elseif ($Command -eq "dev-help") {
    dev-help
} elseif (Get-Command -Name $Command -CommandType Function -ErrorAction SilentlyContinue) {
    & $Command
} else {
    Write-Host "Unknown command: $Command" -ForegroundColor Red
    dev-help
    exit 1
}
