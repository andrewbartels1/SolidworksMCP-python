"""Compatibility shim for the source-backed Prefab dashboard.

Run with:
    prefab serve examples/prefab_cad_assistant/cad_assistant_dashboard.py
    prefab export examples/prefab_cad_assistant/cad_assistant_dashboard.py
"""

from solidworks_mcp.ui.prefab_dashboard import app

__all__ = ["app"]
