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
    $result = micromamba info --json | ConvertFrom-Json
    return $result.envs -contains "$($result.root_prefix)\envs\solidworks_mcp"
}

function dev-help {
    Write-Host "Available Commands:" -ForegroundColor Green
    Write-Host ""
    Write-Host "dev-install     - Install dependencies and setup environment"
    Write-Host "dev-test        - Run test suite with coverage"
    Write-Host "dev-test-full   - Run full suite including real SolidWorks integration tests"
    Write-Host "dev-test-clean  - Remove generated integration test artifacts"
    Write-Host "dev-docs        - Serve documentation locally (http://localhost:8000)"
    Write-Host "dev-build       - Build package for distribution"
    Write-Host "dev-run         - Start the MCP server"
    Write-Host "dev-clean       - Clean build artifacts"
    Write-Host "dev-lint        - Run code linting (ruff)"
    Write-Host "dev-format      - Format code (ruff)"
    Write-Host ""
}

function dev-install {
    Write-Host "Installing SolidWorks MCP Server..." -ForegroundColor Cyan
    micromamba env create -f solidworks_mcp.yml --yes
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Installing Python package in development mode..." -ForegroundColor Cyan
        micromamba run -n solidworks_mcp pip install -e ".[dev,test,docs]"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Installation complete!" -ForegroundColor Green
        } else {
            Write-Host "Failed to install Python package" -ForegroundColor Red
        }
    } else {
        Write-Host "Failed to create conda environment" -ForegroundColor Red
    }
}

function dev-test {
    Write-Host "Running tests with coverage..." -ForegroundColor Cyan
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
    micromamba run -n solidworks_mcp python -m pytest tests/ `
        -m "not solidworks_only" `
        --cov=src/solidworks_mcp `
        --cov-report=term-missing `
        --cov-report=html:htmlcov `
        --cov-report=xml:coverage.xml `
        --durations=10 `
        -v
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Tests passed!" -ForegroundColor Green
        Write-Host "Coverage report: htmlcov/index.html" -ForegroundColor Yellow
    } else {
        Write-Host "Tests failed" -ForegroundColor Red
    }
}

function dev-test-full {
    Write-Host "Running full test suite (including real SolidWorks integration)..." -ForegroundColor Cyan
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
    $env:SOLIDWORKS_MCP_RUN_REAL_INTEGRATION = "true"
    micromamba run -n solidworks_mcp python -m pytest tests/ `
        --cov=src/solidworks_mcp `
        --cov-report=term-missing `
        --cov-report=html:htmlcov `
        --cov-report=xml:coverage.xml `
        --durations=10 `
        -v
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

    micromamba run -n solidworks_mcp python tests/scripts/cleanup_generated_integration_artifacts.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Cleanup complete!" -ForegroundColor Green
        return
    }

    Write-Host "First cleanup attempt failed; retrying after pause..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
    micromamba run -n solidworks_mcp python tests/scripts/cleanup_generated_integration_artifacts.py

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
    micromamba run -n solidworks_mcp mkdocs serve --dev-addr=localhost:8000
}

function dev-build {
    Write-Host "Building package for distribution..." -ForegroundColor Cyan
    micromamba run -n solidworks_mcp python -m build
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Build complete! Package ready in dist/" -ForegroundColor Green
    } else {
        Write-Host "Build failed" -ForegroundColor Red
    }
}

function dev-run {
    Write-Host "Starting MCP server..." -ForegroundColor Cyan
    micromamba run -n solidworks_mcp python -m solidworks_mcp.server
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
    micromamba run -n solidworks_mcp ruff check src/ tests/
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Linting passed!" -ForegroundColor Green
    } else {
        Write-Host "Linting issues found" -ForegroundColor Yellow
    }
}

function dev-format {
    Write-Host "Formatting code (ruff format)..." -ForegroundColor Cyan
    micromamba run -n solidworks_mcp ruff format src/ tests/
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
