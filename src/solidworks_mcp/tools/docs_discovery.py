"""Docs discovery tool for SolidWorks COM and VBA command indexing.

This module provides functionality to discover and catalog all available COM objects,
methods, and properties for the installed SolidWorks version, as well as VBA library
references. Useful for building context for MCP server operations and enabling
intelligent tool selection.
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
except ImportError:  # pragma: no cover
    HAS_WIN32COM = False


# ---------------------------------------------------------------------------
# Known SolidWorks COM interface catalogue (fallback when typelib unavailable)
# ---------------------------------------------------------------------------
_KNOWN_SW_INTERFACES: dict[str, dict[str, list[str]]] = {
    "ISldWorks": {
        "methods": [
            "OpenDoc6",
            "CloseDoc",
            "ActivateDoc3",
            "GetActiveObject",
            "GetFirstDocument",
            "GetDocumentCount",
            "NewDocument",
            "SendMsgToUser2",
            "GetProcessID",
            "ExitApp",
            "RevisionNumber",
            "GetUserTypeLibraryFile",
            "CreateNewDocument",
        ],
        "properties": ["Visible", "ActiveDoc", "FrameState"],
    },
    "IModelDoc2": {
        "methods": [
            "ShowNamedView2",
            "ViewZoomToFit2",
            "SaveBitmapWithVariableSize",
            "SaveAs3",
            "GetTitle",
            "GetPathName",
            "GetType",
            "GetFeatureCount",
            "GetActiveConfiguration",
            "Extension",
            "SketchManager",
            "FeatureManager",
            "SelectionManager",
            "GetMassProperties",
            "Close",
            "SetSaveAsFileName",
            "ResolveAllLightweightComponents",
            "InsertSketch2",
            "SketchAddConstraints",
            "ClearSelection2",
        ],
        "properties": ["ActiveView", "ActiveLayer"],
    },
    "IPartDoc": {
        "methods": [
            "CreateFeatureFromSketch2",
            "AddMateReference",
            "GetBodies2",
            "GetEntityByName",
            "InsertSmartComponents",
            "Material",
        ],
        "properties": [],
    },
    "IAssemblyDoc": {
        "methods": [
            "AddComponent4",
            "AddComponent5",
            "InsertNewPart3",
            "LayoutToAssembly",
            "ResolveAllLightweightComponents",
            "AddMate5",
            "GetComponents",
            "GetComponentCount",
        ],
        "properties": [],
    },
    "IDrawingDoc": {
        "methods": [
            "CreateDrawViewFromModelView3",
            "InsertModelAnnotations3",
            "GenerateViewPalette",
            "Get3DDrawingView",
        ],
        "properties": [],
    },
    "IFeatureManager": {
        "methods": [
            "FeatureExtrusion3",
            "FeatureCut3",
            "FeatureRevolve2",
            "InsertProtrusionBlend4",
            "InsertShell",
            "InsertFillet3",
            "InsertChamfer",
            "InsertDraftXpert3",
            "FeatureMirror3",
            "FeatureCircularPattern2",
            "FeatureLinearPattern3",
            "InsertBoss",
            "FeatureSweep5",
            "FeatureLoft3",
        ],
        "properties": [],
    },
    "ISketchManager": {
        "methods": [
            "InsertSketch",
            "CreateLine",
            "CreateArc",
            "CreateCircle",
            "CreateRectangle",
            "CreateEllipse",
            "CreateSpline",
            "CreateCenterLine",
            "SketchMirror",
            "SketchOffset",
            "AddToDB",
            "InsertSketch2",
        ],
        "properties": ["ActiveSketch"],
    },
    "IModelView": {
        "methods": [
            "SaveBitmapWithVariableSize",
            "ZoomToFit",
            "ZoomToSheet",
            "OrientView",
            "SetCameraParameters",
        ],
        "properties": ["Orientation3", "Translation3"],
    },
    "IExtensionManager": {
        "methods": ["SaveAs2", "SelectByID2", "MultiSelect2"],
        "properties": [],
    },
    "IFeature": {
        "methods": [
            "GetNextFeature",
            "GetName",
            "GetTypeName2",
            "SetSuppression2",
            "IsSuppressed2",
            "GetDefinition",
        ],
        "properties": ["Name"],
    },
    "IBody2": {
        "methods": [
            "GetFaceCount",
            "GetEdgeCount",
            "GetVertexCount",
            "GetMassProperties",
            "GetType",
        ],
        "properties": [],
    },
    "ISketchSegment": {
        "methods": ["GetStartPoint2", "GetEndPoint2", "GetType", "SetEndPoint"],
        "properties": [],
    },
}


def _enumerate_typeinfo_members(typeinfo: Any) -> tuple[list[str], list[str]]:
    """Enumerate methods and properties from a COM ITypeInfo object.

    Uses raw ITypeInfo via pythoncom to walk the function table, which works reliably for
    both early-bound and late-bound COM objects.

    Returns (methods, properties) as sorted de-duped lists.

    Args:
        typeinfo (Any): The typeinfo value.

    Returns:
        tuple[list[str], list[str]]: A tuple containing the resulting values.
    """
    methods: list[str] = []
    properties: list[str] = []
    seen: set[str] = set()

    try:
        typeattr = typeinfo.GetTypeAttr()
        for i in range(typeattr.cFuncs):
            try:
                funcdesc = typeinfo.GetFuncDesc(i)
                names = typeinfo.GetNames(funcdesc.memid)
                name = names[0] if names else None
                if not name or name.startswith("_"):
                    continue
                if name in seen:
                    continue
                seen.add(name)
                # invkind: 1=FUNC, 2=PROPERTYGET, 4=PROPERTYPUT, 8=PROPERTYPUTREF
                if funcdesc.invkind == 1:
                    methods.append(name)
                else:
                    properties.append(name)
            except Exception:
                continue
    except Exception:
        pass

    return sorted(methods), sorted(properties)


def _discover_com_via_typeinfo(sw_app: Any) -> dict[str, Any]:
    """Enumerate ISldWorks methods/properties via ITypeInfo.

    Returns a COM index dict keyed by interface name, with the same shape as the rest of the
    index (``methods``, ``properties``, ``method_count``, ``property_count``).

    Args:
        sw_app (Any): The sw app value.

    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    if not HAS_WIN32COM:
        return {}

    com_index: dict[str, Any] = {}
    total_methods = 0
    total_properties = 0

    try:
        # GetTypeInfo returns ITypeInfo for the IDispatch interface of the object.
        typeinfo = sw_app._oleobj_.GetTypeInfo()
        methods, properties = _enumerate_typeinfo_members(typeinfo)

        # Walk implemented interfaces to catch inherited members.
        try:
            typeattr = typeinfo.GetTypeAttr()
            for impl_idx in range(typeattr.cImplTypes):
                try:
                    ref_type = typeinfo.GetRefTypeOfImplType(impl_idx)
                    ref_typeinfo = typeinfo.GetRefTypeInfo(ref_type)
                    extra_m, extra_p = _enumerate_typeinfo_members(ref_typeinfo)
                    for m in extra_m:
                        if m not in methods:
                            methods.append(m)
                    for p in extra_p:
                        if p not in properties:
                            properties.append(p)
                except Exception:
                    continue
        except Exception:
            pass

        methods = sorted(set(methods))
        properties = sorted(set(properties))

        if methods or properties:
            com_index["ISldWorks"] = {
                "methods": methods,
                "properties": properties,
                "method_count": len(methods),
                "property_count": len(properties),
            }
            total_methods += len(methods)
            total_properties += len(properties)

    except Exception as exc:
        logger.debug(
            "[docs_discovery] ITypeInfo enumeration unavailable; using built-in interface catalog fallback: {}",
            exc,
        )

    return com_index, total_methods, total_properties


def _discover_vba_references_via_registry() -> dict[str, Any]:
    """Enumerate VBA/TypeLib references via the Windows Registry.

    Scans HKEY_CLASSES_ROOT\TypeLib for entries whose name or GUID matches SolidWorks or
    common Office/VBA libraries.

    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    vba_refs: dict[str, Any] = {}

    # Keywords to look for in type lib names
    interesting_keywords = [
        "solidworks",
        "sldworks",
        "vba",
        "visual basic",
        "stdole",
        "office",
        "microsoft office",
    ]

    if platform.system() != "Windows":
        return vba_refs

    try:
        import winreg

        typelib_key = winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, "TypeLib", access=winreg.KEY_READ
        )
        idx = 0
        while True:
            try:
                guid = winreg.EnumKey(typelib_key, idx)
                idx += 1
            except OSError:
                break
            try:
                guid_key = winreg.OpenKey(typelib_key, guid, access=winreg.KEY_READ)
                ver_idx = 0
                while True:
                    try:
                        version = winreg.EnumKey(guid_key, ver_idx)
                        ver_idx += 1
                    except OSError:
                        break
                    try:
                        ver_key = winreg.OpenKey(
                            guid_key, version, access=winreg.KEY_READ
                        )
                        try:
                            name, _ = winreg.QueryValueEx(ver_key, "")
                        except OSError:
                            name = ""
                        winreg.CloseKey(ver_key)
                        if name and any(
                            kw in name.lower() for kw in interesting_keywords
                        ):
                            key = f"{name} ({guid} v{version})"
                            if key not in vba_refs:
                                vba_refs[key] = {
                                    "description": name,
                                    "guid": guid,
                                    "version": version,
                                    "status": "available",
                                }
                    except Exception:
                        continue
                winreg.CloseKey(guid_key)
            except Exception:
                continue
        winreg.CloseKey(typelib_key)
    except Exception as exc:
        logger.debug("[docs_discovery] Registry TypeLib scan failed: {}", exc)

    return vba_refs


class SolidWorksDocsDiscovery:
    """Discover and index SolidWorks COM and VBA documentation.

    Args:
        output_dir (Path | None): The output dir value. Defaults to None.

    Attributes:
        output_dir (Any): The output dir value.
        sw_app (Any): The sw app value.
    """

    def __init__(self, output_dir: Path | None = None):
        """Initialize docs discovery.

        Args:
            output_dir (Path | None): The output dir value. Defaults to None.

        Returns:
            Any: The result produced by the operation.
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
            bool: True if connect to solidworks, otherwise False.
        """
        if not HAS_WIN32COM:
            logger.error("win32com not available; cannot index COM")
            return False

        if platform.system() != "Windows":
            logger.error("COM discovery only available on Windows")
            return False

        try:
            # Prefer GetActiveObject so we attach to a running SolidWorks session.
            # EnsureDispatch is used (instead of Dispatch) so that the type library
            # is loaded and pythoncom ITypeInfo enumeration works correctly.
            try:
                self.sw_app = win32com.client.GetActiveObject("SldWorks.Application")
            except com_error:
                logger.warning(
                    "SolidWorks not running; attempting to create new instance"
                )
                self.sw_app = win32com.client.gencache.EnsureDispatch(
                    "SldWorks.Application"
                )
            return True
        except com_error as e:
            logger.error(f"Failed to connect to SolidWorks: {e}")
            return False

    def discover_com_objects(self) -> dict[str, Any]:
        """Discover all COM objects and their methods/properties.

        Uses ITypeInfo enumeration via pythoncom for ISldWorks, then supplements with the active
        document's interface if a model is open. Falls back to the known-interface catalogue
        when typelib introspection is unavailable.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
        """
        if not self.sw_app:
            logger.error("Not connected to SolidWorks")
            return {}

        com_index: dict[str, Any] = {}
        total_m = 0
        total_p = 0

        # ------------------------------------------------------------------ #
        # Primary: ITypeInfo enumeration for ISldWorks
        # ------------------------------------------------------------------ #
        if HAS_WIN32COM:
            try:
                result = _discover_com_via_typeinfo(self.sw_app)
                # _discover_com_via_typeinfo returns (dict, total_m, total_p)
                partial_index, t_m, t_p = result
                com_index.update(partial_index)
                total_m += t_m
                total_p += t_p
                if partial_index:
                    logger.info(
                        "[docs_discovery] ITypeInfo: {} ISldWorks methods, {} properties",
                        t_m,
                        t_p,
                    )
            except Exception as exc:
                logger.debug("[docs_discovery] ITypeInfo path failed: {}", exc)

        # ------------------------------------------------------------------ #
        # Supplement: active document (IModelDoc2) if a model is open
        # ------------------------------------------------------------------ #
        try:
            active_doc = self.sw_app.ActiveDoc
            if active_doc is not None and HAS_WIN32COM:
                doc_typeinfo = active_doc._oleobj_.GetTypeInfo()
                doc_methods, doc_props = _enumerate_typeinfo_members(doc_typeinfo)
                if doc_methods or doc_props:
                    com_index["IModelDoc2_active"] = {
                        "methods": doc_methods,
                        "properties": doc_props,
                        "method_count": len(doc_methods),
                        "property_count": len(doc_props),
                    }
                    total_m += len(doc_methods)
                    total_p += len(doc_props)
                    logger.info(
                        "[docs_discovery] Active doc typeinfo: {} methods, {} properties",
                        len(doc_methods),
                        len(doc_props),
                    )
        except Exception:
            pass

        # ------------------------------------------------------------------ #
        # Fallback: merge known-interface catalogue for any gaps
        # ------------------------------------------------------------------ #
        for iface_name, members in _KNOWN_SW_INTERFACES.items():
            if iface_name in com_index:
                continue  # already populated via typeinfo
            com_index[iface_name] = {
                "methods": members["methods"],
                "properties": members["properties"],
                "method_count": len(members["methods"]),
                "property_count": len(members["properties"]),
            }
            total_m += len(members["methods"])
            total_p += len(members["properties"])

        try:
            self.index["total_methods"] += total_m
            self.index["total_properties"] += total_p
        except TypeError:
            pass  # accumulator corrupted (e.g. set to a string by tests); tolerate

        # Get SolidWorks version
        try:
            self.index["solidworks_version"] = self.sw_app.RevisionNumber()
        except Exception:
            pass

        return com_index

    def discover_vba_references(self) -> dict[str, Any]:
        """Discover VBA/TypeLib references via the Windows Registry.

        Scans HKEY_CLASSES_ROOT\TypeLib for SolidWorks and common Office/VBA type libraries.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
        """
        refs = _discover_vba_references_via_registry()
        if refs:
            logger.info(
                "[docs_discovery] Registry TypeLib scan found {} entries", len(refs)
            )
        else:
            logger.debug(
                "[docs_discovery] Registry TypeLib scan found no matching entries"
            )
        return refs

    def discover_all(self) -> dict[str, Any]:
        """Run full discovery of COM and VBA documentation.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
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
            filename (str): The filename value. Defaults to "solidworks_docs_index.json".

        Returns:
            Path | None: The result produced by the operation.
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
            dict[str, Any]: A dictionary containing the resulting values.
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
    """Input schema for docs discovery.

    Attributes:
        include_vba (bool): The include vba value.
        output_dir (str | None): The output dir value.
        year (int | None): The year value.
    """

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
    """Input schema for SolidWorks API help search.

    Attributes:
        auto_discover_if_missing (bool): The auto discover if missing value.
        index_file (str | None): The index file value.
        max_results (int): The max results value.
        query (str): The query value.
        year (int | None): The year value.
    """

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
    """Normalize dict/model payloads for direct tool invocation paths.

    Args:
        input_data (Any): The input data value.
        model_type (type[CompatInputT]): The model type value.

    Returns:
        CompatInputT: The result produced by the operation.
    """
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
    """Extract a 4-digit year from any string.

    Args:
        value (str | None): The value value.

    Returns:
        int | None: The result produced by the operation.
    """
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
    """Detect the latest installed SolidWorks year from the public samples path.

    Returns:
        int | None: The result produced by the operation.
    """
    root = Path(r"C:\Users\Public\Documents\SOLIDWORKS")
    if not root.exists():
        return None

    years: list[int] = []
    try:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            year = _extract_year(child.name)
            if year is not None:
                years.append(year)
    except OSError:
        # Path can be inaccessible or missing on CI runners and non-Windows hosts.
        return None

    if not years:
        return None
    return max(years)


def _resolve_solidworks_year(requested_year: int | None, config: Any) -> int | None:
    """Resolve SolidWorks year from explicit request, config, then local installation.

    Args:
        requested_year (int | None): The requested year value.
        config (Any): Configuration values for the operation.

    Returns:
        int | None: The result produced by the operation.
    """
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
    """Load docs index JSON from disk.

    Args:
        index_file (Path): The index file value.

    Returns:
        dict[str, Any] | None: A dictionary containing the resulting values.
    """
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
    """Find the most appropriate index file for a requested year.

    Args:
        year (int | None): The year value.
        explicit_index_file (str | None): The explicit index file value.

    Returns:
        Path | None: The result produced by the operation.
    """
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
    """Search indexed COM objects/members for a query.

    Args:
        index (dict[str, Any]): The index value.
        query (str): Query text used for the operation.
        max_results (int): The max results value.

    Returns:
        list[dict[str, Any]]: A list containing the resulting items.
    """
    tokens = [t for t in re.split(r"\s+", query.lower().strip()) if t]
    if not tokens:
        return []

    results: list[dict[str, Any]] = []

    def _score(text: str) -> int:
        """Build internal score.

        Args:
            text (str): Input text processed by the operation.

        Returns:
            int: The computed numeric result.
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
    """Provide coherent fallback help when no docs index is available.

    Args:
        query (str): Query text used for the operation.

    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
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
        mcp (Any): The mcp value.
        adapter (Any): Adapter instance used for the operation.
        config (dict[str, Any]): Configuration values for the operation.

    Returns:
        int: The computed numeric result.
    """

    @mcp.tool()  # type: ignore[untyped-decorator]
    async def discover_solidworks_docs(
        input_data: DiscoverDocsInput | None = None,
    ) -> dict[str, Any]:
        """Discover and index SolidWorks COM and VBA documentation.

        Creates a searchable index of all available COM objects, methods, properties, and VBA
        libraries for the installed SolidWorks version. Useful for building context for
        intelligent MCP tool selection and documentation queries.

        Args:
            input_data (DiscoverDocsInput | None): The input data value. Defaults to None.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

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

            # Rebuild the FAISS RAG namespace so Gemma can query the API surface.
            rag_indexed = False
            if output_file is not None:
                try:
                    from solidworks_mcp.agents.vector_rag import (
                        build_solidworks_api_docs_index,
                    )

                    rag_idx = build_solidworks_api_docs_index(output_file)
                    rag_idx.save()
                    rag_indexed = True
                    logger.info(
                        "FAISS 'solidworks-api-docs' namespace rebuilt: %d chunks",
                        rag_idx.chunk_count,
                    )
                except ImportError:
                    logger.debug("faiss-cpu not installed; skipping RAG index rebuild")
                except Exception as _rag_exc:
                    logger.warning("RAG rebuild failed: {}", _rag_exc)

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
                "rag_indexed": rag_indexed,
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

        This tool helps when the LLM gets stuck by mapping user intent to discovered COM members
        and practical MCP workflow guidance.

        Args:
            input_data (SearchApiHelpInput | None): The input data value. Defaults to None.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
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
