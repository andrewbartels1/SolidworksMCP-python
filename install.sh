#!/bin/zsh
set -e

echo "🚀 SolidWorks MCP Python - Installing Dependencies"
echo "================================================"
echo "📦 Installing dependencies only..."
echo ""

# Function to find conda command (check micromamba first since it's often aliased as mamba)
find_conda_cmd() {
    if command -v micromamba &> /dev/null; then
        echo "micromamba"
    elif command -v mamba &> /dev/null; then
        echo "mamba"
    elif command -v conda &> /dev/null; then
        echo "conda"
    else
        echo ""
    fi
}

# Find conda command
CONDA_CMD=$(find_conda_cmd)
if [ -z "$CONDA_CMD" ]; then
    echo "❌ Error: No conda/mamba/micromamba found. Please install one first."
    echo "💡 Try: brew install micromamba  # or install miniconda"
    exit 1
fi

echo "📦 Using package manager: $CONDA_CMD"

# TODO(beginner-docs): Keep this checklist in sync with docs/getting-started/installation.md
# and replace with a full step-by-step WSL<->Windows setup walkthrough.
# Required beginner flow to document clearly:
# 1) Windows host installs SolidWorks + Python + pywin32 and runs MCP server.
# 2) WSL/Linux installs only client/development deps (no pywin32/COM).
# 3) WSL client connects to Windows-hosted server over localhost/LAN.
# 4) Include first-run verification commands from both Windows and WSL shells.

# Surface platform-specific dependency behavior early to avoid confusion.
if [ "$(uname -s)" != "MINGW64_NT" ] && [ "$(uname -s)" != "MSYS_NT" ] && [ "$(uname -s)" != "CYGWIN_NT" ] && [ "$(uname -s)" != "Windows_NT" ]; then
    echo ""
    echo "⚠️  Non-Windows environment detected: $(uname -s)"
    echo "ℹ️  pywin32 is Windows-only and will be skipped by dependency markers."
    echo "ℹ️  To use real SolidWorks COM automation, run this server with Windows Python"
    echo "   on your Windows host, then connect to it remotely from WSL/containers."
    echo ""
fi

# Remove any existing environment
echo "🧹 Removing existing environment if it exists..."
$CONDA_CMD env remove -n solidworks_mcp --yes 2>/dev/null || echo "ℹ️  No existing environment found"

echo "🏗️  Creating environment from solidworks_mcp.yml..."
$CONDA_CMD env create -f solidworks_mcp.yml --yes

if [ $? -ne 0 ]; then
    echo "❌ Failed to create conda environment"
    exit 1
fi

echo "📥 Installing Python package in development mode..."
$CONDA_CMD run -n solidworks_mcp pip install -e ".[dev,docs]"

if [ $? -ne 0 ]; then
    echo "❌ Failed to install Python package"
    exit 1
fi

echo ""
echo "✅ Installation complete!"
echo "========================"
echo ""
echo "🎯 To activate the environment:"
echo "   $CONDA_CMD activate solidworks_mcp"
echo ""
echo ""
echo "🔧 For development:"
echo "   • Format code: make format"
echo "   • Run tests: make test"
echo "   • Build docs: make docs"
echo "   • Check coverage: python validate_coverage.py"
echo ""
echo "🔒 Security configurations available in examples/configurations/"
echo ""
echo "For full documentation, visit: http://localhost:8000 (after running 'make docs-serve')"