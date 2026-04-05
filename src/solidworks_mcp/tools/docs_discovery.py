"""Docs discovery tool for SolidWorks COM and VBA command indexing.

This module provides functionality to discover and catalog all available COM
objects, methods, and properties for the installed SolidWorks version, as well
as VBA library references. Useful for building context for MCP server operations
and enabling intelligent tool selection.
"""

from __future__ import annotations

import json
import platform
import re
from pathlib import Path
from typing import Any, TypeVar

from loguru import logger
from pydantic import Field

from .input_compat import CompatInput

try:
    import win32com.client
    from pywintypes import com_error

    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False


_KNOWN_COM_MEMBER_CANDIDATES: dict[str, dict[str, list[str]]] = {
    "ISldWorks": {
        "methods": [
            "RevisionNumber",
            "OpenDoc6",
            "CloseDoc",
            "ActivateDoc3",
            "GetProcessID",
        ],
        "properties": ["Visible", "ActiveDoc"],
    }
}


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
            # pywin32 requires exactly one of Pathname or Class.
            self.sw_app = win32com.client.GetObject(Class="SldWorks.Application")
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
                if obj_ref is None and obj_name != "ISldWorks":
                    # Skip abstract interfaces without concrete instances.
                    continue

                obj = obj_ref if obj_ref is not None else self.sw_app

                methods = []
                properties = []

                # Extract methods and properties from COM object.
                # Use the instance (not its type) so COM dispatch attributes are
                # visible. win32com's __getattr__ returns a bound-method wrapper
                # for COM methods (callable) and the property value for properties
                # (typically not callable), letting callable() distinguish them.
                try:
                    for attr_name in dir(obj):
                        if not attr_name.startswith("_"):
                            try:
                                attr = getattr(obj, attr_name, None)
                            except Exception:
                                attr = None
                            if callable(attr):
                                methods.append(attr_name)
                            else:
                                properties.append(attr_name)
                except Exception as e:
                    logger.debug(f"Error extracting attributes from {obj_name}: {e}")

                if not methods and not properties:
                    fallback = _KNOWN_COM_MEMBER_CANDIDATES.get(obj_name, {})
                    for attr_name in fallback.get("methods", []):
                        try:
                            attr = getattr(obj, attr_name, None)
                        except Exception:
                            continue
                        if callable(attr):
                            methods.append(attr_name)
                    for attr_name in fallback.get("properties", []):
                        try:
                            attr = getattr(obj, attr_name, None)
                        except Exception:
                            continue
                        if not callable(attr):
                            properties.append(attr_name)

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
                # Use Class= keyword only; passing pathname="" alongside Class raises
                # "must specify Pathname or Class, but not both" in win32com.
                lib = (
                    win32com.client.GetObject(Class=lib_name) if HAS_WIN32COM else None
                )
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
                    "status": "not_available",
                    "note": str(e),
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
    year: int | None = Field(
        default=None,
        description="SolidWorks year override for saved index naming (e.g., 2026)",
    )


class SearchApiHelpInput(CompatInput):
    """Input schema for SolidWorks API help search."""

    query: str = Field(
        description="Search phrase for SolidWorks API help (methods, properties, objects)",
        min_length=2,
    )
    year: int | None = Field(
        default=None,
        description="SolidWorks year override (e.g., 2025, 2026)",
    )
    max_results: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of search results",
    )
    index_file: str | None = Field(
        default=None,
        description="Optional explicit index file path (JSON) to search",
    )
    auto_discover_if_missing: bool = Field(
        default=False,
        description="Generate docs index first when no index file is found",
    )


CompatInputT = TypeVar("CompatInputT", bound=CompatInput)


def _normalize_input(input_data: Any, model_type: type[CompatInputT]) -> CompatInputT:
    """Normalize dict/model payloads for direct tool invocation paths."""
    if input_data is None:
        return model_type()
    if isinstance(input_data, model_type):
        return input_data
    if isinstance(input_data, dict):
        return model_type.model_validate(input_data)
    if hasattr(input_data, "model_dump"):
        return model_type.model_validate(input_data.model_dump())
    return model_type.model_validate(input_data)


def _extract_year(value: str | None) -> int | None:
    """Extract a 4-digit year from any string."""
    if not value:
        return None
    match = re.search(r"\b(20\d{2})\b", value)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _detect_installed_solidworks_year() -> int | None:
    """Detect the latest installed SolidWorks year from the public samples path."""
    root = Path(r"C:\Users\Public\Documents\SOLIDWORKS")
    if not root.exists():
        return None

    years: list[int] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        year = _extract_year(child.name)
        if year is not None:
            years.append(year)

    if not years:
        return None
    return max(years)


def _resolve_solidworks_year(requested_year: int | None, config: Any) -> int | None:
    """Resolve SolidWorks year from explicit request, config, then local installation."""
    if requested_year:
        return requested_year

    config_year = getattr(config, "solidworks_year", None)
    if isinstance(config_year, int):
        return config_year

    config_path_year = _extract_year(getattr(config, "solidworks_path", None))
    if config_path_year:
        return config_path_year

    return _detect_installed_solidworks_year()


def _load_index_file(index_file: Path) -> dict[str, Any] | None:
    """Load docs index JSON from disk."""
    try:
        if not index_file.exists() or not index_file.is_file():
            return None
        with index_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
        return None
    except Exception:
        return None


def _find_index_file(year: int | None, explicit_index_file: str | None) -> Path | None:
    """Find the most appropriate index file for a requested year."""
    if explicit_index_file:
        explicit = Path(explicit_index_file)
        if explicit.exists():
            return explicit

    names = ["solidworks_docs_index.json"]
    if year:
        names.insert(0, f"solidworks_docs_index_{year}.json")

    search_dirs = [
        Path(".generated/docs-index"),
        Path("tests/.generated/solidworks_integration/docs-index"),
        Path("tests/.generated/docs-index"),
    ]

    for directory in search_dirs:
        for name in names:
            candidate = directory / name
            if candidate.exists():
                return candidate

    return None


def _search_index(
    index: dict[str, Any], query: str, max_results: int
) -> list[dict[str, Any]]:
    """Search indexed COM objects/members for a query."""
    tokens = [t for t in re.split(r"\s+", query.lower().strip()) if t]
    if not tokens:
        return []

    results: list[dict[str, Any]] = []

    def _score(text: str) -> int:
        """Execute score.

        Args:
            text (str): Describe text.

        Returns:
            int: Describe the returned value.

        """
        lower = text.lower()
        score = 0
        for token in tokens:
            if token == lower:
                score += 10
            elif token in lower:
                score += 3
        return score

    for obj_name, obj_data in index.get("com_objects", {}).items():
        obj_score = _score(obj_name)

        for method in obj_data.get("methods", []):
            score = obj_score + _score(str(method))
            if score > 0:
                results.append(
                    {
                        "object": obj_name,
                        "member": method,
                        "member_type": "method",
                        "score": score,
                    }
                )

        for prop in obj_data.get("properties", []):
            score = obj_score + _score(str(prop))
            if score > 0:
                results.append(
                    {
                        "object": obj_name,
                        "member": prop,
                        "member_type": "property",
                        "score": score,
                    }
                )

    for lib_name, lib_data in index.get("vba_references", {}).items():
        lib_text = f"{lib_name} {lib_data.get('description', '')}"
        score = _score(lib_text)
        if score > 0:
            results.append(
                {
                    "object": "VBA Library",
                    "member": lib_name,
                    "member_type": "reference",
                    "status": lib_data.get("status", "unknown"),
                    "score": score,
                }
            )

    results.sort(key=lambda item: item.get("score", 0), reverse=True)
    return results[:max_results]


def _fallback_help_for_query(query: str) -> dict[str, Any]:
    """Provide coherent fallback help when no docs index is available."""
    q = query.lower()

    if any(word in q for word in ("revolve", "lathe", "turned")):
        return {
            "suggested_tools": [
                "create_part",
                "create_sketch",
                "add_centerline",
                "add_line",
                "add_arc",
                "exit_sketch",
                "create_revolve",
            ],
            "next_steps": [
                "Create a profile sketch and a centerline in the same sketch.",
                "Exit sketch mode before create_revolve.",
                "If real COM returns parameter mismatch, use generate_vba_revolve as fallback guidance.",
            ],
        }

    if any(word in q for word in ("extrude", "boss", "cut")):
        return {
            "suggested_tools": [
                "create_part",
                "create_sketch",
                "add_rectangle",
                "add_circle",
                "exit_sketch",
                "create_extrusion",
            ],
            "next_steps": [
                "Ensure sketch profile is closed before create_extrusion.",
                "Use direction='cut' for removal operations.",
            ],
        }

    return {
        "suggested_tools": [
            "discover_solidworks_docs",
            "open_model",
            "get_file_properties",
            "save_as",
        ],
        "next_steps": [
            "Run discover_solidworks_docs to index the local COM API surface.",
            "Search again with a narrower API term like a method or interface name.",
        ],
    }


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

    @mcp.tool()  # type: ignore[untyped-decorator]
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
            normalized = _normalize_input(input_data, DiscoverDocsInput)
            output_dir = Path(normalized.output_dir) if normalized.output_dir else None
            year = _resolve_solidworks_year(normalized.year, config)

            discovery = SolidWorksDocsDiscovery(output_dir=output_dir)

            logger.info("Starting SolidWorks documentation discovery...")
            index = discovery.discover_all()

            filename = (
                f"solidworks_docs_index_{year}.json"
                if year
                else "solidworks_docs_index.json"
            )
            output_file = discovery.save_index(filename=filename)

            summary = discovery.create_search_summary()

            return {
                "status": "success",
                "message": f"Discovered {summary['total_com_objects']} COM objects, "
                f"{summary['total_methods']} methods, "
                f"{summary['total_properties']} properties",
                "index": index,
                "summary": summary,
                "year": year,
                "output_file": str(output_file) if output_file else None,
                "execution_time": time.time() - start_time,
            }

        except Exception as e:
            logger.error(f"Error during docs discovery: {e}")
            return {
                "status": "error",
                "message": f"Discovery failed: {str(e)}",
            }

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def search_solidworks_api_help(
        input_data: SearchApiHelpInput | None = None,
    ) -> dict[str, Any]:
        """Search SolidWorks API help index and return coherent guidance.

        This tool helps when the LLM gets stuck by mapping user intent to
        discovered COM members and practical MCP workflow guidance.
        """

        import time

        start_time = time.time()

        try:
            normalized = _normalize_input(input_data, SearchApiHelpInput)
            year = _resolve_solidworks_year(normalized.year, config)

            index_file = _find_index_file(year, normalized.index_file)
            index = _load_index_file(index_file) if index_file else None

            if index is None and normalized.auto_discover_if_missing:
                if HAS_WIN32COM and platform.system() == "Windows":
                    discovery = SolidWorksDocsDiscovery()
                    index = discovery.discover_all()
                    filename = (
                        f"solidworks_docs_index_{year}.json"
                        if year
                        else "solidworks_docs_index.json"
                    )
                    index_file = discovery.save_index(filename=filename)

            matches = _search_index(
                index or {}, normalized.query, normalized.max_results
            )
            fallback = _fallback_help_for_query(normalized.query)

            guidance_lines = []
            if matches:
                guidance_lines.append(
                    f"Found {len(matches)} API matches for '{normalized.query}'."
                )
                guidance_lines.append(
                    "Start with the highest-score members and verify with the real adapter path."
                )
            else:
                guidance_lines.append(
                    "No indexed API hits found; using workflow fallback guidance."
                )
                guidance_lines.append(
                    "Consider running discover_solidworks_docs first for this machine/version."
                )

            return {
                "status": "success",
                "message": "SolidWorks API help search completed",
                "query": normalized.query,
                "year": year,
                "source_index_file": str(index_file) if index_file else None,
                "matches": matches,
                "fallback_help": fallback,
                "guidance": " ".join(guidance_lines),
                "execution_time": time.time() - start_time,
            }

        except Exception as e:
            logger.error(f"Error during SolidWorks API help search: {e}")
            return {
                "status": "error",
                "message": f"API help search failed: {str(e)}",
            }

    tool_count = 2  # discover_solidworks_docs, search_solidworks_api_help
    return tool_count
