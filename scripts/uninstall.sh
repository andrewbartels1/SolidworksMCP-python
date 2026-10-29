#!/bin/zsh
set -e

echo "🗑️  SolidWorks MCP Python - Removing Dependencies"
echo "==============================================="
echo "🧹 Removing environment and dependencies..."
echo ""

# Function to find conda command
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
    echo "❌ Error: No conda/mamba/micromamba found. Cannot remove environment."
    exit 1
fi

echo "📦 Using package manager: $CONDA_CMD"

# Remove environment
echo "🗑️  Removing environment 'solidworks_mcp'..."
$CONDA_CMD env remove -n solidworks_mcp --yes 2>/dev/null || echo "ℹ️  Environment 'solidworks_mcp' not found"

echo "🧹 Cleaning up build artifacts..."
rm -rf build/ dist/ *.egg-info/ src/*.egg-info/ site/ .pytest_cache/ htmlcov/ .coverage 2>/dev/null || true

echo ""
echo "✅ Uninstallation complete!"
echo ""