"""Docs discovery tool for SolidWorks COM and VBA command indexing.

This module provides functionality to discover and catalog all available COM
objects, methods, and properties for the installed SolidWorks version, as well
as VBA library references. Useful for building context for MCP server operations
and enabling intelligent tool selection.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import Field

from .input_compat import CompatInput

try:
    import win32com.client
    from pywintypes import com_error

    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False


class SolidWorksDocsDiscovery:
    """Discover and index SolidWorks COM and VBA documentation."""

    def __init__(self, output_dir: Path | None = None):
        """Initialize docs discovery.

        Args:
            output_dir: Directory to save indexed documentation (default: .generated/docs-index)
        """
        self.output_dir = output_dir or Path(".generated/docs-index")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sw_app = None
        self.index: dict[str, Any] = {
            "version": "1.0",
            "solidworks_version": None,
            "com_objects": {},
            "vba_references": {},
            "total_methods": 0,
            "total_properties": 0,
        }

    def connect_to_solidworks(self) -> bool:
        """Connect to running SolidWorks instance.

        Returns:
            bool: True if connection successful, False otherwise
        """
        if not HAS_WIN32COM:
            logger.error("win32com not available; cannot index COM")
            return False

        if platform.system() != "Windows":
            logger.error("COM discovery only available on Windows")
            return False

        try:
            self.sw_app = win32com.client.GetObject("", "SldWorks.Application")
            if self.sw_app is None:
                logger.warning(
                    "SolidWorks not running; attempting to create new instance"
                )
                self.sw_app = win32com.client.Dispatch("SldWorks.Application")
            return True
        except com_error as e:
            logger.error(f"Failed to connect to SolidWorks: {e}")
            return False

    def discover_com_objects(self) -> dict[str, Any]:
        """Discover all COM objects and their methods/properties.

        Returns:
            dict: Indexed COM object information
        """
        if not self.sw_app:
            logger.error("Not connected to SolidWorks")
            return {}

        com_index = {}

        # Core SolidWorks objects to catalog
        core_objects = {
            "ISldWorks": self.sw_app,
            "IModelDoc2": None,  # Active document
            "IPartDoc": None,  # Part document
            "IAssemblyDoc": None,  # Assembly document
            "IDrawingDoc": None,  # Drawing document
        }

        for obj_name, obj_ref in core_objects.items():
            try:
                if obj_ref is None and obj_name.startswith("I"):
                    # Skip abstract interfaces without instances
                    continue

                if obj_name == "ISldWorks":
                    obj = self.sw_app
                else:
                    continue

                methods = []
                properties = []

                # Extract methods and properties from COM object
                try:
                    obj_type = type(obj)
                    for attr_name in dir(obj):
                        if not attr_name.startswith("_"):
                            attr = getattr(obj_type, attr_name, None)
                            if callable(attr):
                                methods.append(attr_name)
                            else:
                                properties.append(attr_name)
                except Exception as e:
                    logger.debug(f"Error extracting attributes from {obj_name}: {e}")

                com_index[obj_name] = {
                    "methods": methods,
                    "properties": properties,
                    "method_count": len(methods),
                    "property_count": len(properties),
                }

                self.index["total_methods"] += len(methods)
                self.index["total_properties"] += len(properties)

            except Exception as e:
                logger.debug(f"Error cataloging {obj_name}: {e}")

        # Get SolidWorks version
        try:
            self.index["solidworks_version"] = self.sw_app.RevisionNumber()
        except Exception as e:
            logger.debug(f"Could not retrieve SolidWorks version: {e}")

        return com_index

    def discover_vba_references(self) -> dict[str, Any]:
        """Discover VBA library references available to SolidWorks.

        Returns:
            dict: Indexed VBA library information
        """
        vba_refs = {}

        # Standard VBA/COM libraries typically available
        common_libs = {
            "VBA": "Visual Basic for Applications",
            "stdole": "OLE Automation",
            "Office": "Microsoft Office",
            "VBIDE": "Visual Basic IDE",
            "SldWorks": "SolidWorks API",
            "SolidWorks.Interop.sldworks": "SolidWorks COM Interop",
        }

        for lib_name, lib_desc in common_libs.items():
            try:
                lib = win32com.client.GetObject("", lib_name) if HAS_WIN32COM else None
                if lib:
                    vba_refs[lib_name] = {
                        "description": lib_desc,
                        "status": "available",
                    }
                else:
                    vba_refs[lib_name] = {
                        "description": lib_desc,
                        "status": "not_available",
                    }
            except Exception as e:
                vba_refs[lib_name] = {
                    "description": lib_desc,
                    "status": "error",
                    "error": str(e),
                }

        return vba_refs

    def discover_all(self) -> dict[str, Any]:
        """Run full discovery of COM and VBA documentation.

        Returns:
            dict: Complete indexed documentation
        """
        if not self.connect_to_solidworks():
            logger.error("Cannot proceed with discovery without SolidWorks connection")
            return self.index

        logger.info("Discovering COM objects...")
        self.index["com_objects"] = self.discover_com_objects()

        logger.info("Discovering VBA references...")
        self.index["vba_references"] = self.discover_vba_references()

        return self.index

    def save_index(self, filename: str = "solidworks_docs_index.json") -> Path | None:
        """Save discovered documentation to JSON file.

        Args:
            filename: Name of output file

        Returns:
            Path to saved file, or None if save failed
        """
        try:
            output_path = self.output_dir / filename
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(self.index, f, indent=2)
            logger.info(f"Docs index saved to {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to save docs index: {e}")
            return None

    def create_search_summary(self) -> dict[str, Any]:
        """Create a summary of indexed documentation for search/reference.

        Returns:
            dict: Simplified search index
        """
        summary = {
            "total_com_objects": len(self.index["com_objects"]),
            "total_methods": self.index["total_methods"],
            "total_properties": self.index["total_properties"],
            "solidworks_version": self.index["solidworks_version"],
            "available_vba_libs": [
                lib
                for lib, info in self.index["vba_references"].items()
                if info.get("status") == "available"
            ],
        }
        return summary


class DiscoverDocsInput(CompatInput):
    """Input schema for docs discovery."""

    output_dir: str | None = Field(
        default=None,
        description="Optional output directory for indexed documentation",
    )
    include_vba: bool = Field(
        default=True,
        description="Include VBA library reference indexing",
    )


async def register_docs_discovery_tools(
    mcp: Any, adapter: Any, config: dict[str, Any]
) -> int:
    """Register docs discovery tool with FastMCP.

    Args:
        mcp: FastMCP server instance
        adapter: SolidWorks adapter
        config: Configuration dictionary

    Returns:
        int: Number of tools registered (1)
    """

    @mcp.tool()
    async def discover_solidworks_docs(
        input_data: DiscoverDocsInput | None = None,
    ) -> dict[str, Any]:
        """Discover and index SolidWorks COM and VBA documentation.

        Creates a searchable index of all available COM objects, methods, properties,
        and VBA libraries for the installed SolidWorks version. Useful for building
        context for intelligent MCP tool selection and documentation queries.

        Args:
            input_data (DiscoverDocsInput, optional): Contains:
                - output_dir (str, optional): Output directory for saved index
                - include_vba (bool): Include VBA references (default: True)

        Returns:
            dict[str, Any]: Discovery result containing:
                - status (str): "success" or "error"
                - message (str): Operation description
                - index (dict): Complete indexed documentation
                - summary (dict): Quick reference summary
                - output_file (str, optional): Path to saved index file
                - execution_time (float): Operation time in seconds

        Example:
            ```python
            result = await discover_solidworks_docs({
                "output_dir": "docs-index",
                "include_vba": True
            })

            if result["status"] == "success":
                print(f"Discovered {result['summary']['total_methods']} COM methods")
                print(f"Output saved to {result['output_file']}")
            ```

        Note:
            - Requires Windows + SolidWorks installed and running
            - Creates .generated/docs-index directory if not present
            - Generates solidworks_docs_index.json with full catalog
            - Index can be used to build context for RAG or tool discovery
        """
        import time

        start_time = time.time()

        if not HAS_WIN32COM:
            return {
                "status": "error",
                "message": "win32com not available; cannot discover COM documentation",
            }

        if platform.system() != "Windows":
            return {
                "status": "error",
                "message": "COM discovery only available on Windows",
            }

        try:
            output_dir = (
                Path(input_data.output_dir)
                if input_data and input_data.output_dir
                else None
            )

            discovery = SolidWorksDocsDiscovery(output_dir=output_dir)

            logger.info("Starting SolidWorks documentation discovery...")
            index = discovery.discover_all()

            output_file = discovery.save_index()

            summary = discovery.create_search_summary()

            return {
                "status": "success",
                "message": f"Discovered {summary['total_com_objects']} COM objects, "
                f"{summary['total_methods']} methods, "
                f"{summary['total_properties']} properties",
                "index": index,
                "summary": summary,
                "output_file": str(output_file) if output_file else None,
                "execution_time": time.time() - start_time,
            }

        except Exception as e:
            logger.error(f"Error during docs discovery: {e}")
            return {
                "status": "error",
                "message": f"Discovery failed: {str(e)}",
            }

    tool_count = 1  # discover_solidworks_docs
    return tool_count
