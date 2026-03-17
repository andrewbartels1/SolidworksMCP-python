"""
Pytest test runner configuration and utilities.

This module provides test discovery, coverage reporting, and integration
test execution for the SolidWorks MCP Server.
"""

import os
import sys
from pathlib import Path

# Add src directory to Python path for test imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Set environment variables for testing
os.environ.setdefault("USE_MOCK_SOLIDWORKS", "true")
os.environ.setdefault("SOLIDWORKS_MCP_LOG_LEVEL", "DEBUG")
os.environ.setdefault("SOLIDWORKS_MCP_MOCK_SOLIDWORKS", "true")
