"""Docs discovery tool for SolidWorks COM and VBA command indexing.

Builds an index of every SolidWorks COM interface, with each member's
signature and description, from the registered SolidWorks type library, plus
the VBA library references in the registry. The API lookup tools answer from
that index and build it themselves the first time, so an agent never has to
prepare anything: SolidWorks only has to be installed.

Index records (:mod:`.type_library`) and lookup results (below) are Pydantic
models; the tools return them as plain dicts with ``model_dump()``, like
every other tool in the package.
"""

from __future__ import annotations

import json
import platform
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar

from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel, Field, TypeAdapter

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import ToolOperationError, normalize_input, with_tool_boundary
from .type_library import (
    Access,
    ApiMember,
    ApiMethod,
    ApiParameter,
    ApiProperty,
    TypeLibraryUnavailable,
    index_type_library,
    load_type_library,
    target_version,
    year_of,
)

# Index files written before the index came from the type library are "1.0";
# their member lists were largely hand-typed and are never answered from.
INDEX_FORMAT = "2.0"

#: Where lookups look for a saved index, in order.
_INDEX_DIRS = (
    Path(".generated/docs-index"),
    Path("tests/.generated/solidworks_integration/docs-index"),
    Path("tests/.generated/docs-index"),
)

IndexStatus = Literal["ready", "rebuilt", "unavailable"]
MemberType = Literal["method", "property"]

#: Validates one saved member record into its model.
_MEMBER: TypeAdapter[ApiMethod | ApiProperty] = TypeAdapter(ApiMember)

#: Each interface record's name lists, by member type.
_MEMBER_LISTS: tuple[tuple[MemberType, str], ...] = (
    ("method", "methods"),
    ("property", "properties"),
)


def _discover_vba_references_via_registry() -> dict[str, Any]:
    """Enumerate VBA/TypeLib references via the Windows Registry.

    Scans HKEY_CLASSES_ROOT\\TypeLib for entries whose name matches
    SolidWorks or common Office/VBA libraries.

    Returns:
        dict[str, Any]: ``"<name> (<guid> v<version>)"`` -> its description,
        GUID, version and status; empty off Windows.
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

    The COM part is read from the registered SolidWorks type library, so it
    needs SolidWorks installed but never starts, attaches to or calls it.

    Args:
        output_dir (Path | None): Where the index is saved. Defaults to
            ``.generated/docs-index``.
        year (int | None): The SolidWorks year whose type library to read;
            None for the newest installed.
        strict_year (bool): True when the caller asked for ``year``, so a
            missing year is an error instead of falling back to the newest.

    Attributes:
        output_dir (Path): Where the index is saved.
        index (dict[str, Any]): The index built so far, as saved.
    """

    def __init__(
        self,
        output_dir: Path | None = None,
        year: int | None = None,
        strict_year: bool = False,
    ):
        """Initialize docs discovery.

        Args:
            output_dir (Path | None): Where the index is saved.
            year (int | None): The SolidWorks year to read, if any.
            strict_year (bool): True to fail when that year isn't installed.
        """
        self.output_dir = output_dir or _INDEX_DIRS[0]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.year = year
        self.strict_year = strict_year
        self.index: dict[str, Any] = {
            "version": INDEX_FORMAT,
            "type_library": None,
            "solidworks_version": None,
            "com_objects": {},
            "vba_references": {},
            "total_methods": 0,
            "total_properties": 0,
        }

    def discover_com_objects(self) -> dict[str, Any]:
        """Index every COM interface in the SolidWorks type library.

        Also records which type library was read and the member totals.

        Returns:
            dict[str, Any]: Interface name -> its methods, properties and
            member signatures, as saved.

        Raises:
            TypeLibraryUnavailable: No matching type library is registered.
        """
        lib, info = load_type_library(self.year, self.strict_year)
        interfaces = index_type_library(lib)
        self.index["type_library"] = info.model_dump()
        self.index["solidworks_version"] = info.version
        self.index["total_methods"] = sum(i.method_count for i in interfaces.values())
        self.index["total_properties"] = sum(
            i.property_count for i in interfaces.values()
        )
        logger.info(
            "[docs_discovery] Type library {} ({}): {} interfaces",
            info.version,
            info.path,
            len(interfaces),
        )
        return {name: record.model_dump() for name, record in interfaces.items()}

    def discover_vba_references(self) -> dict[str, Any]:
        """Discover VBA/TypeLib references via the Windows Registry.

        Returns:
            dict[str, Any]: The SolidWorks and Office/VBA type libraries
            found; empty off Windows.
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

    def discover_all(self, include_vba: bool = True) -> dict[str, Any]:
        """Run full discovery of COM and, optionally, VBA documentation.

        Args:
            include_vba (bool): Also scan the registry for VBA references.

        Returns:
            dict[str, Any]: The complete index.

        Raises:
            TypeLibraryUnavailable: No matching type library is registered.
        """
        logger.info("Discovering COM objects...")
        self.index["com_objects"] = self.discover_com_objects()

        if include_vba:
            logger.info("Discovering VBA references...")
            self.index["vba_references"] = self.discover_vba_references()

        return self.index

    def save_index(self, filename: str = "solidworks_docs_index.json") -> Path:
        """Save the index as compact JSON.

        Args:
            filename (str): The file name inside ``output_dir``.

        Returns:
            Path: The saved file.

        Raises:
            ToolOperationError: The file could not be written. Lookups would
                otherwise rebuild the index on every call.
        """
        output_path = self.output_dir / filename
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                # Compact: every lookup reads this file, and nobody edits it.
                json.dump(self.index, f, separators=(",", ":"))
        except OSError as exc:
            raise ToolOperationError(
                f"Couldn't save the API index to {output_path}: {exc}"
            ) from exc
        logger.info("Docs index saved to {}", output_path)
        return output_path

    def create_search_summary(self) -> dict[str, Any]:
        """Summarize the index for a response.

        Returns:
            dict[str, Any]: Interface, method and property totals, the type
            library version and the VBA libraries found.
        """
        return {
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


class DiscoverDocsInput(CompatInput):
    """Input schema for ``discover_solidworks_docs``.

    Attributes:
        output_dir (str | None): Folder to save the index in.
        include_vba (bool): Whether to scan for VBA library references.
        year (int | None): The SolidWorks year whose type library to read.
    """

    output_dir: str | None = Field(
        default=None,
        description=(
            "Folder to save the index in; default .generated/docs-index. The "
            "lookups only read the default folder, so another folder is for "
            "keeping a copy (pass it back as index_file)."
        ),
    )
    include_vba: bool = Field(
        default=True,
        description="Also list the VBA type libraries registered on this machine",
    )
    year: int | None = Field(
        default=None,
        ge=1995,
        le=2100,
        description=(
            "SolidWorks year whose type library to read, e.g. 2026; an error "
            "if that year isn't installed. Unset: the year the server was "
            "started with (--year), else the newest installed."
        ),
    )


class ApiIndexInput(CompatInput):
    """Fields every API lookup takes to choose the index it answers from.

    Attributes:
        year (int | None): The SolidWorks year whose API to answer for.
        index_file (str | None): A saved index to answer from instead.
    """

    year: int | None = Field(
        default=None,
        ge=1995,
        le=2100,
        description=(
            "SolidWorks year whose API to answer for, e.g. 2026. Usually "
            "leave unset: the server's --year, else the newest installed. A "
            "year that isn't installed is explained in the result's note."
        ),
    )
    index_file: str | None = Field(
        default=None,
        description=(
            "Path to a saved index JSON to answer from instead of the "
            "installed type library, e.g. one copied from another machine. "
            "Rarely needed."
        ),
    )


class SearchApiHelpInput(ApiIndexInput):
    """Input schema for ``search_solidworks_api_help``.

    Attributes:
        query (str): Words to search member and interface names for.
        max_results (int): How many matches to return at most.
        auto_discover_if_missing (bool): Accepted for old callers; unused.
    """

    query: str = Field(
        description=(
            "Words to find in interface and member names, e.g. 'chamfer' or "
            "'SelectByID2'"
        ),
        min_length=2,
    )
    max_results: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of matches to return",
    )
    auto_discover_if_missing: bool = Field(
        default=False,
        description=(
            "No longer needed: the index is built automatically when missing. "
            "Still accepted so existing callers keep working."
        ),
    )


class LookupApiMethodInput(ApiIndexInput):
    """Input schema for ``lookup_api_method``.

    Attributes:
        interface (str): The COM interface the member is on.
        method (str): The method or property name.
    """

    interface: str = Field(
        description="COM interface name, e.g. 'IFeatureManager' or 'IModelDoc2'",
        min_length=2,
    )
    method: str = Field(
        description=(
            "Method or property name, e.g. 'InsertFeatureChamfer'; case does not matter"
        ),
        min_length=1,
    )


class LookupApiInterfaceInput(ApiIndexInput):
    """Input schema for ``lookup_api_interface``.

    Attributes:
        interface (str): The COM interface whose members to list.
    """

    interface: str = Field(
        description="COM interface name, e.g. 'ISldWorks'; case does not matter",
        min_length=2,
    )


class FindRelatedApiInput(ApiIndexInput):
    """Input schema for ``find_related_api_members``.

    Attributes:
        name (str): An interface or member name to find relatives of.
        max_results (int): How many related members to return at most.
    """

    name: str = Field(
        description=(
            "An interface name (lists its members) or a member name (lists "
            "the members beside it), e.g. 'InsertSketch'"
        ),
        min_length=2,
    )
    max_results: int = Field(
        default=25, ge=1, le=200, description="Maximum related members to return"
    )


class MemberLookup(BaseModel):
    """``lookup_api_method``'s result: one member's signature, or no match.

    Attributes:
        found (bool): Whether the member is on the interface.
        interface (str): The interface, as SolidWorks spells it when found.
        method (str | None): The name asked for, on a no-match.
        member (str | None): The member's real name.
        member_type (MemberType | None): ``method`` or ``property``.
        signature_indexed (bool | None): Always true on a match.
        description (str | None): The help string.
        parameters (list[ApiParameter] | None): The parameters.
        return_type (str | None): The return type (a property's value type).
        access (Access | None): A property's access.
        note (str | None): Why there's no match, or a casing difference.
    """

    found: bool = Field(description="True when the member is on the interface")
    interface: str = Field(description="Interface name")
    method: str | None = Field(default=None, description="Name asked for (no match)")
    member: str | None = Field(
        default=None, description="The member's name as SolidWorks spells it"
    )
    member_type: MemberType | None = Field(
        default=None, description="method or property"
    )
    signature_indexed: bool | None = Field(
        default=None, description="Always true on a match"
    )
    description: str | None = Field(default=None, description="One-line help string")
    parameters: list[ApiParameter] | None = Field(
        default=None, description="Parameters in call order; empty for a property"
    )
    return_type: str | None = Field(
        default=None,
        description="Returned type (a property's value type); null for nothing",
    )
    access: Access | None = Field(default=None, description="A property's access")
    note: str | None = Field(
        default=None, description="Why there is no match, or a casing difference"
    )


class InterfaceLookup(BaseModel):
    """``lookup_api_interface``'s result.

    Attributes:
        found (bool): Whether the interface is indexed.
        interface (str): Its name, as SolidWorks spells it when found.
        methods (list[str] | None): Its method names.
        properties (list[str] | None): Its property names.
        method_count (int | None): How many methods.
        property_count (int | None): How many properties.
        note (str | None): Why no index could be built.
    """

    found: bool = Field(description="True when the interface is indexed")
    interface: str = Field(description="Interface name")
    methods: list[str] | None = Field(default=None, description="Method names")
    properties: list[str] | None = Field(default=None, description="Property names")
    method_count: int | None = Field(default=None, description="Number of methods")
    property_count: int | None = Field(default=None, description="Number of properties")
    note: str | None = Field(default=None, description="Why no index could be built")


class SearchMatch(BaseModel):
    """One ``search_solidworks_api_help`` match.

    Attributes:
        object (str): The interface, or ``VBA Library``.
        member (str): The member or library name.
        member_type (str): ``method``, ``property`` or ``reference``.
        score (int): Relevance; higher is better.
        status (str | None): A VBA library's status.
    """

    object: str = Field(description="Interface name, or 'VBA Library'")
    member: str = Field(description="Member or library name")
    member_type: Literal["method", "property", "reference"] = Field(
        description="method, property or reference (a VBA library)"
    )
    score: int = Field(description="Relevance; higher is better")
    status: str | None = Field(default=None, description="A VBA library's status")


class RelatedMember(BaseModel):
    """One member ``find_related_api_members`` returns.

    Attributes:
        object (str): The interface it is on.
        member (str): Its name.
        member_type (MemberType): ``method`` or ``property``.
        reason (str): Why it is related.
    """

    object: str = Field(description="Interface the member is on")
    member: str = Field(description="Member name")
    member_type: MemberType = Field(description="method or property")
    reason: str = Field(
        description="'same interface', 'sibling on <interface>' or 'name match'"
    )


class RelatedLookup(BaseModel):
    """``find_related_api_members``'s result.

    Attributes:
        found (bool): Whether anything related was found.
        query (str): The name asked for.
        resolved_as (str): How the name was read.
        related (list[RelatedMember]): The related members.
        note (str | None): Why no index could be built.
    """

    found: bool = Field(description="True when anything related was found")
    query: str = Field(description="The name asked for")
    resolved_as: Literal["interface", "member", "name-match"] = Field(
        description="interface, member, or name-match (a substring of names)"
    )
    related: list[RelatedMember] = Field(description="Related members")
    note: str | None = Field(default=None, description="Why no index could be built")


def _extract_year(value: str | None) -> int | None:
    """Extract a 4-digit year (20xx) from a string such as an install path.

    Args:
        value (str | None): The text to search.

    Returns:
        int | None: The year, or None when there isn't one.
    """
    if not value:
        return None
    match = re.search(r"\b(20\d{2})\b", value)
    return int(match.group(1)) if match else None


def _resolve_solidworks_year(requested_year: int | None, config: Any) -> int | None:
    """The year a call asked for, else the year the server was started with.

    Never guessed from folder names: those can be missing, or left behind by
    an uninstalled version. None means "the newest installed".

    Args:
        requested_year (int | None): The year the call asked for.
        config (Any): Server configuration (``solidworks_year`` is set by
            ``--year``; ``solidworks_path`` may name a year).

    Returns:
        int | None: The year, or None.
    """
    if requested_year:
        return requested_year
    config_year = getattr(config, "solidworks_year", None)
    if isinstance(config_year, int):
        return config_year
    return _extract_year(getattr(config, "solidworks_path", None))


def _load_index_file(index_file: Path) -> dict[str, Any] | None:
    """Read a saved index.

    Args:
        index_file (Path): The JSON file.

    Returns:
        dict[str, Any] | None: The index, or None when the file is missing
        or isn't a JSON object.
    """
    try:
        with index_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _find_index_file(year: int) -> Path | None:
    """Find the saved index for a SolidWorks year.

    Args:
        year (int): The type library's year.

    Returns:
        Path | None: The first ``solidworks_docs_index_<year>.json`` in the
        index folders, or None.
    """
    for directory in _INDEX_DIRS:
        candidate = directory / f"solidworks_docs_index_{year}.json"
        if candidate.is_file():
            return candidate
    return None


def _index_is_stale(index_file: Path | None, max_age_days: int) -> bool:
    """Whether an index file is older than ``max_age_days``.

    Args:
        index_file (Path | None): The file, if any.
        max_age_days (int): The age limit in days.

    Returns:
        bool: True when the file exists and is older than the limit.
    """
    if index_file is None:
        return False
    try:
        age_days = (time.time() - index_file.stat().st_mtime) / 86400.0
    except OSError:
        return False
    return age_days > max_age_days


def _build_index(
    year: int | None,
    strict: bool,
    output_dir: Path | None = None,
    include_vba: bool = True,
) -> tuple[SolidWorksDocsDiscovery, Path]:
    """Build the docs index from the type library and save it under its year.

    Args:
        year (int | None): The SolidWorks year to read; None for the newest.
        strict (bool): True when the caller asked for ``year``.
        output_dir (Path | None): Where to save; the default index folder if None.
        include_vba (bool): Also scan for VBA references.

    Returns:
        tuple[SolidWorksDocsDiscovery, Path]: The discovery holding the
        index, and the saved file.

    Raises:
        TypeLibraryUnavailable: No matching type library is registered.
        ToolOperationError: The index could not be saved.
    """
    discovery = SolidWorksDocsDiscovery(
        output_dir=output_dir, year=year, strict_year=strict
    )
    index = discovery.discover_all(include_vba=include_vba)
    filename = f"solidworks_docs_index_{index['type_library']['year']}.json"
    return discovery, discovery.save_index(filename=filename)


def _maybe_refresh_index(
    index: dict[str, Any], index_file: Path, year: int, config: Any
) -> tuple[dict[str, Any], Path]:
    """Rebuild a current index that is old, when the config allows.

    A SolidWorks service pack can replace the type library in place, so an
    index older than ``docs_index_max_age_days`` is rebuilt when
    ``config.docs_index_auto_refresh`` is on. Any failure keeps the existing
    index.

    Args:
        index (dict[str, Any]): The saved index.
        index_file (Path): Its file.
        year (int): The type library's year.
        config (Any): Server configuration.

    Returns:
        tuple[dict[str, Any], Path]: The (possibly rebuilt) index and file.
    """
    if not getattr(config, "docs_index_auto_refresh", False):
        return index, index_file
    max_age = int(getattr(config, "docs_index_max_age_days", 21) or 21)
    if not _index_is_stale(index_file, max_age):
        return index, index_file
    logger.info("Docs index older than {} days; rebuilding it", max_age)
    try:
        discovery, fresh_file = _build_index(year, strict=False)
    except TypeLibraryUnavailable as exc:
        logger.warning("Docs index refresh failed, using existing index: {}", exc)
        return index, index_file
    return discovery.index, fresh_file


_LookupResultT = TypeVar("_LookupResultT", MemberLookup, InterfaceLookup, RelatedLookup)


@dataclass(frozen=True)
class _IndexForLookup:
    """The index a lookup answers from, and how it was obtained.

    Attributes:
        index (dict[str, Any]): The index; empty when ``status`` is
            ``unavailable``.
        index_file (Path | None): The file it was read from or saved to.
        status (IndexStatus): ``ready`` (read from disk), ``rebuilt`` (built
            for this call) or ``unavailable``.
        note (str | None): Why the index is unavailable.
        year (int | None): The year asked for, reported when the index
            doesn't name its type library (none could be built, or a
            caller's file lacks it).
    """

    index: dict[str, Any]
    index_file: Path | None
    status: IndexStatus
    note: str | None = None
    year: int | None = None

    def annotate(self, result: _LookupResultT) -> _LookupResultT:
        """Add why no index could be built to a lookup result, when it couldn't.

        Args:
            result (_LookupResultT): A lookup result.

        Returns:
            _LookupResultT: The same result.
        """
        if self.note:
            result.note = self.note
        return result

    def payload(self) -> dict[str, Any]:
        """The fields every lookup response carries about its index.

        Returns:
            dict[str, Any]: ``year`` and ``type_library_version`` of the
            library that answered, ``index_status`` and ``source_index_file``.
        """
        library = self.index.get("type_library") or {}
        return {
            "year": library.get("year", self.year),
            "type_library_version": library.get("version"),
            "index_status": self.status,
            "source_index_file": str(self.index_file) if self.index_file else None,
        }


def _index_for_lookup(
    requested_year: int | None, explicit_index_file: str | None, config: Any
) -> _IndexForLookup:
    """Find the saved index for the type library a lookup reads, or build it.

    The index is found by the type library version the registry says would
    be read, so it is built once and reused, whatever year was guessed. An
    index in an older format, or from another type library version, is
    rebuilt, never answered from. A usable ``explicit_index_file`` is
    answered from directly, with no registry read.

    Args:
        requested_year (int | None): The year the caller asked for, if any.
        explicit_index_file (str | None): An index file the caller named.
        config (Any): Server configuration.

    Returns:
        _IndexForLookup: The index and how it was obtained.

    Raises:
        ToolOperationError: A built index could not be saved.
    """
    year = _resolve_solidworks_year(requested_year, config)
    if explicit_index_file:
        explicit = Path(explicit_index_file)
        index = _load_index_file(explicit)
        if index is not None and index.get("version") == INDEX_FORMAT:
            return _IndexForLookup(index, explicit, "ready", year=year)
    strict = requested_year is not None
    try:
        major, minor = target_version(year, strict)
    except TypeLibraryUnavailable as exc:
        return _IndexForLookup({}, None, "unavailable", str(exc), year)
    library_year = year_of(major)
    index_file = _find_index_file(library_year)
    index = _load_index_file(index_file) if index_file else None
    if (
        index_file is not None
        and index is not None
        and index.get("version") == INDEX_FORMAT
        and (index.get("type_library") or {}).get("version") == f"{major}.{minor}"
    ):
        index, index_file = _maybe_refresh_index(
            index, index_file, library_year, config
        )
        return _IndexForLookup(index, index_file, "ready")
    try:
        discovery, fresh_file = _build_index(library_year, strict=True)
    except TypeLibraryUnavailable as exc:
        return _IndexForLookup({}, None, "unavailable", str(exc), year)
    return _IndexForLookup(discovery.index, fresh_file, "rebuilt")


def _search_index(
    index: dict[str, Any], query: str, max_results: int
) -> list[SearchMatch]:
    """Search the index's interface, member and VBA library names.

    Args:
        index (dict[str, Any]): The index.
        query (str): Words to look for; each word scores separately.
        max_results (int): How many matches to keep.

    Returns:
        list[SearchMatch]: The best matches, highest score first.
    """
    tokens = [t for t in re.split(r"\s+", query.lower().strip()) if t]
    if not tokens:
        return []

    results: list[SearchMatch] = []

    def _score(text: str) -> int:
        """Score a name: 10 per word equal to it, 3 per word inside it.

        Args:
            text (str): The name.

        Returns:
            int: The score.
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
        for member_type, key in _MEMBER_LISTS:
            for member in obj_data.get(key, []):
                score = obj_score + _score(str(member))
                if score > 0:
                    results.append(
                        SearchMatch(
                            object=obj_name,
                            member=str(member),
                            member_type=member_type,
                            score=score,
                        )
                    )

    for lib_name, lib_data in index.get("vba_references", {}).items():
        score = _score(f"{lib_name} {lib_data.get('description', '')}")
        if score > 0:
            results.append(
                SearchMatch(
                    object="VBA Library",
                    member=lib_name,
                    member_type="reference",
                    status=lib_data.get("status", "unknown"),
                    score=score,
                )
            )

    results.sort(key=lambda item: item.score, reverse=True)
    return results[:max_results]


def _resolve_interface(
    index: dict[str, Any], name: str
) -> tuple[str, dict[str, Any]] | None:
    """Find an interface by name, ignoring case.

    Args:
        index (dict[str, Any]): The index.
        name (str): The interface name asked for.

    Returns:
        tuple[str, dict[str, Any]] | None: Its real name and record, or None.
    """
    com_objects = index.get("com_objects", {})
    if name in com_objects:
        return name, com_objects[name]
    lowered = name.lower()
    for obj_name, obj_data in com_objects.items():
        if obj_name.lower() == lowered:
            return obj_name, obj_data
    return None


def _lookup_interface(index: dict[str, Any], interface: str) -> InterfaceLookup:
    """List an interface's methods and properties, or say it isn't indexed.

    Args:
        index (dict[str, Any]): The index.
        interface (str): The interface name asked for.

    Returns:
        InterfaceLookup: Its member names and counts, or a no-match.
    """
    resolved = _resolve_interface(index, interface)
    if resolved is None:
        return InterfaceLookup(found=False, interface=interface)
    obj_name, obj_data = resolved
    methods = [str(m) for m in obj_data.get("methods", [])]
    properties = [str(p) for p in obj_data.get("properties", [])]
    return InterfaceLookup(
        found=True,
        interface=obj_name,
        methods=methods,
        properties=properties,
        method_count=len(methods),
        property_count=len(properties),
    )


def _lookup_method(index: dict[str, Any], interface: str, method: str) -> MemberLookup:
    """Look up a method or property's signature on an interface.

    Matching ignores case, as COM late binding does; ``member`` is the name
    as the type library spells it. Only the matched record is validated.

    Args:
        index (dict[str, Any]): The index.
        interface (str): The interface name asked for.
        method (str): The member name asked for.

    Returns:
        MemberLookup: The signature, or a no-match with a note.
    """
    resolved = _resolve_interface(index, interface)
    if resolved is None:
        return MemberLookup(found=False, interface=interface, method=method)
    obj_name, obj_data = resolved
    lowered = method.lower()
    for name, raw in obj_data.get("members", {}).items():
        if name.lower() != lowered:
            continue
        record = _MEMBER.validate_python(raw)
        result = MemberLookup(
            found=True,
            interface=obj_name,
            member=name,
            member_type=record.kind,
            signature_indexed=True,
            description=record.description,
        )
        if isinstance(record, ApiProperty):
            # A property's "return type" is the value type it reads back.
            result.parameters = []
            result.return_type = record.type
            result.access = record.access
        else:
            result.parameters = record.parameters
            result.return_type = record.return_type
        if name != method:
            result.note = (
                f"SolidWorks spells it {name!r}. COM matches names "
                f"regardless of case, so {method!r} also works."
            )
        return result
    return MemberLookup(
        found=False,
        interface=obj_name,
        method=method,
        note=f"{method!r} is not an indexed member of {obj_name}.",
    )


def _find_related_api_members(
    index: dict[str, Any], name: str, max_results: int
) -> RelatedLookup:
    """Given an indexed interface or member name, return related members.

    - An interface name -> its own members.
    - A member name -> the other members of every interface that also exposes
      it (siblings commonly used together), plus name-substring matches
      elsewhere in the index.

    Args:
        index (dict[str, Any]): The index.
        name (str): The interface or member name.
        max_results (int): How many related members to keep.

    Returns:
        RelatedLookup: The related members and how ``name`` was read.
    """
    com_objects = index.get("com_objects", {})
    related: list[RelatedMember] = []
    seen: set[tuple[str, str]] = set()

    def _add(obj_name: str, member: str, member_type: MemberType, reason: str) -> None:
        """Record one related member, once, never the name asked about.

        Args:
            obj_name (str): Its interface.
            member (str): Its name.
            member_type (MemberType): ``method`` or ``property``.
            reason (str): Why it is related.
        """
        key = (obj_name, str(member))
        if key in seen or str(member).lower() == name.lower():
            return
        seen.add(key)
        related.append(
            RelatedMember(
                object=obj_name,
                member=str(member),
                member_type=member_type,
                reason=reason,
            )
        )

    resolved = _resolve_interface(index, name)
    if resolved is not None:
        obj_name, obj_data = resolved
        for m in obj_data.get("methods", []):
            _add(obj_name, m, "method", "same interface")
        for p in obj_data.get("properties", []):
            _add(obj_name, p, "property", "same interface")
        return RelatedLookup(
            found=True,
            query=name,
            resolved_as="interface",
            related=related[:max_results],
        )

    lowered = name.lower()
    matched_member = False
    for obj_name, obj_data in com_objects.items():
        members: list[tuple[str, MemberType]] = [
            (str(member), member_type)
            for member_type, key in _MEMBER_LISTS
            for member in obj_data.get(key, [])
        ]
        names_lower = {str(m).lower() for m, _ in members}
        if lowered in names_lower:
            matched_member = True
            for member, member_type in members:
                _add(obj_name, member, member_type, f"sibling on {obj_name}")
        else:
            for member, member_type in members:
                if lowered in str(member).lower():
                    _add(obj_name, member, member_type, "name match")

    return RelatedLookup(
        found=matched_member or bool(related),
        query=name,
        resolved_as="member" if matched_member else "name-match",
        related=related[:max_results],
    )


def _fallback_help_for_query(query: str) -> dict[str, Any]:
    """Suggest MCP tools for a query, alongside or instead of API matches.

    Args:
        query (str): The search words.

    Returns:
        dict[str, Any]: ``suggested_tools`` and ``next_steps``.
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
            "lookup_api_interface",
            "lookup_api_method",
            "find_related_api_members",
        ],
        "next_steps": [
            "Search again with a narrower term, such as part of a method name.",
            "Use lookup_api_interface on an interface (e.g. IModelDoc2) to see "
            "every member it has.",
        ],
    }


def _rebuild_rag_index(index_file: Path) -> bool:
    """Rebuild the FAISS ``solidworks-api-docs`` namespace from a saved index.

    Optional: it needs the ``faiss-cpu`` extra, and a failure here never
    fails the discovery that triggered it.

    Args:
        index_file (Path): The saved docs index.

    Returns:
        bool: True when the RAG index was rebuilt and saved.
    """
    try:
        from solidworks_mcp.agents.vector_rag import build_solidworks_api_docs_index

        rag_idx = build_solidworks_api_docs_index(index_file)
        rag_idx.save()
    except ImportError:
        logger.debug("faiss-cpu not installed; skipping RAG index rebuild")
        return False
    except Exception as exc:
        logger.warning("RAG rebuild failed: {}", exc)
        return False
    logger.info(
        "FAISS 'solidworks-api-docs' namespace rebuilt: {} chunks",
        rag_idx.chunk_count,
    )
    return True


async def register_docs_discovery_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register the docs discovery and API lookup tools with FastMCP.

    None of them use the adapter or SolidWorks itself: they read the
    installed type library.

    Args:
        mcp (FastMCP): The server to register on.
        adapter (SolidWorksAdapter): Unused; kept for the registrar's
            uniform signature.
        config (dict[str, Any]): Server configuration (``solidworks_year``,
            the index refresh settings).

    Returns:
        int: The number of tools registered.
    """
    mcp = with_tool_boundary(mcp)

    @mcp.tool()
    async def discover_solidworks_docs(
        input_data: DiscoverDocsInput | None = None,
    ) -> dict[str, Any]:
        """Rebuild the SolidWorks API index on purpose. The lookups don't need it.

        The lookup tools (lookup_api_method, lookup_api_interface,
        find_related_api_members, search_solidworks_api_help) build the index
        themselves on first use, so call this only to rebuild it, to read a
        specific SolidWorks year, or to save a copy elsewhere. It reads every
        interface in the installed SolidWorks type library (each member's
        parameters, return type and description), plus the VBA library
        references. SolidWorks must be installed, not running; it is never
        started or called. Changes: writes the index file, replacing the
        saved one.

        Returns ``summary`` (interface, method and property counts),
        ``type_library`` (version, year and .tlb path), ``year`` and
        ``output_file``, the saved index (megabytes, so it is not returned).
        Fails with a message naming the installed years when ``year`` isn't
        installed, or saying SolidWorks isn't installed here.

        Example input: ``{"year": 2026}``

        Args:
            input_data (DiscoverDocsInput | None): The rebuild. Nothing is
                required: `year` defaults to the installed release,
                `output_dir` to the index folder, and `include_vba` to on.

        Returns:
            dict[str, Any]: ``summary``, ``type_library``, ``year``,
            ``output_file`` and ``rag_indexed``, plus
            ``status``/``message``/``execution_time``.
        """
        start_time = time.time()
        normalized = normalize_input(input_data, DiscoverDocsInput)
        output_dir = Path(normalized.output_dir) if normalized.output_dir else None
        year = _resolve_solidworks_year(normalized.year, config)

        logger.info("Starting SolidWorks documentation discovery...")
        discovery, output_file = _build_index(
            year,
            strict=normalized.year is not None,
            output_dir=output_dir,
            include_vba=normalized.include_vba,
        )
        index = discovery.index
        summary = discovery.create_search_summary()

        return {
            "status": "success",
            "message": f"Discovered {summary['total_com_objects']} COM objects, "
            f"{summary['total_methods']} methods, "
            f"{summary['total_properties']} properties",
            "type_library": index["type_library"],
            "summary": summary,
            "year": index["type_library"]["year"],
            "output_file": str(output_file),
            "rag_indexed": _rebuild_rag_index(output_file),
            "execution_time": time.time() - start_time,
        }

    @mcp.tool()
    async def search_solidworks_api_help(
        input_data: SearchApiHelpInput | None = None,
    ) -> dict[str, Any]:
        """Search SolidWorks API interface and member names by keyword.

        Use this when you don't know the exact name: "chamfer" finds
        IFeatureManager.InsertFeatureChamfer. Then call lookup_api_method on
        a match for its parameters and return type. Matches come from the
        SolidWorks type library installed on this machine.

        Setup: none. SolidWorks must be installed, not running; it is never
        contacted. Read-only. The first call builds the index (about a
        second) and later calls reuse it. ``index_status`` is ``ready``
        (saved index), ``rebuilt`` (built for this call) or ``unavailable``
        (no index could be built; ``guidance`` says why).

        Returns ``matches`` (interface, member, member_type, score),
        ``guidance``, and ``fallback_help`` suggesting MCP tools for the
        task, with ``year`` and ``type_library_version`` of the library that
        answered.

        Example input: ``{"query": "chamfer", "max_results": 5}``

        Args:
            input_data (SearchApiHelpInput | None): The search. `query`
                (one or more words) is required; `max_results` and `year`
                have defaults.

        Returns:
            dict[str, Any]: ``matches``, ``guidance``, ``fallback_help``,
            ``year``, ``type_library_version``, ``index_status`` and
            ``source_index_file``, plus ``status``/``message``/``execution_time``.
        """
        start_time = time.time()
        normalized = normalize_input(input_data, SearchApiHelpInput)
        source = _index_for_lookup(normalized.year, normalized.index_file, config)

        matches = _search_index(source.index, normalized.query, normalized.max_results)
        guidance_lines = []
        if matches:
            guidance_lines.append(
                f"Found {len(matches)} API matches for '{normalized.query}'."
            )
            guidance_lines.append(
                "Use lookup_api_method on a match for its parameters and return type."
            )
        else:
            guidance_lines.append(
                "No indexed API hits found; using workflow fallback guidance."
            )
        if source.note:
            guidance_lines.append(source.note)

        return {
            "status": "success",
            "message": "SolidWorks API help search completed",
            "query": normalized.query,
            **source.payload(),
            "matches": [match.model_dump(exclude_unset=True) for match in matches],
            "fallback_help": _fallback_help_for_query(normalized.query),
            "guidance": " ".join(guidance_lines),
            "execution_time": time.time() - start_time,
        }

    @mcp.tool()
    async def lookup_api_method(
        input_data: LookupApiMethodInput | None = None,
    ) -> dict[str, Any]:
        """Look up one SolidWorks API method or property: parameters, return type, description.

        Use this before writing or debugging a SolidWorks API call (VBA, a
        macro or COM) to check that the member exists on that interface and
        how to call it. Answers come from the SolidWorks type library
        installed on this machine, so they match the installed version.

        Setup: none. SolidWorks must be installed, not running; it is never
        contacted. Read-only. The first lookup builds the index (about a
        second). ``index_status`` is ``ready``, ``rebuilt`` or
        ``unavailable``.

        Names match regardless of case, as COM does. ``result.member`` is
        SolidWorks' own spelling, with a ``note`` when yours differs. Each
        parameter has a ``type`` and a ``direction``: ``in``, ``out``
        (SolidWorks fills it) or ``in_out`` (pass a variable by reference).
        ``return_type`` is null when the method returns nothing; a property
        has its value type there and an ``access``. ``result.found`` false
        means there is no such member, and ``result.note`` says why,
        including when no index could be built (SolidWorks isn't installed
        here, or the requested year isn't).

        Example input: ``{"interface": "ISldWorks", "method": "OpenDoc6"}``

        Args:
            input_data (LookupApiMethodInput | None): The member to look up.
                `interface` (e.g. "ISldWorks") and `method` (a method or
                property name) are required; `year` has a default.

        Returns:
            dict[str, Any]: ``result``, ``year``, ``type_library_version``,
            ``index_status`` and ``source_index_file``, plus
            ``status``/``message``/``execution_time``.
        """
        start_time = time.time()
        normalized = normalize_input(input_data, LookupApiMethodInput)
        source = _index_for_lookup(normalized.year, normalized.index_file, config)
        result = source.annotate(
            _lookup_method(source.index, normalized.interface, normalized.method)
        )
        return {
            "status": "success",
            "message": (
                "Method found"
                if result.found
                else "No indexed match for that interface/method"
            ),
            **source.payload(),
            "result": result.model_dump(exclude_unset=True),
            "execution_time": time.time() - start_time,
        }

    @mcp.tool()
    async def lookup_api_interface(
        input_data: LookupApiInterfaceInput | None = None,
    ) -> dict[str, Any]:
        """List every method and property of a SolidWorks COM interface.

        Use this to see what an interface offers, such as IFeatureManager,
        or to check which interface a member is really on before calling it.
        For one member's parameters, use lookup_api_method. Names match
        regardless of case.

        Setup: none. SolidWorks must be installed, not running; it is never
        contacted. Read-only. The first call builds the index (about a
        second) and later calls reuse it. ``index_status`` is ``ready``
        (saved index), ``rebuilt`` (built for this call) or ``unavailable``
        (no index could be built).

        Returns ``result`` with ``methods``, ``properties`` and their counts.
        ``result.found`` false means the interface isn't in the type library,
        or no index could be built, in which case ``result.note`` says why.

        Example input: ``{"interface": "IFeatureManager"}``

        Args:
            input_data (LookupApiInterfaceInput | None): The interface.
                `interface` (e.g. "IFeatureManager") is required; `year` has
                a default.

        Returns:
            dict[str, Any]: ``result``, ``year``, ``type_library_version``,
            ``index_status`` and ``source_index_file``, plus
            ``status``/``message``/``execution_time``.
        """
        start_time = time.time()
        normalized = normalize_input(input_data, LookupApiInterfaceInput)
        source = _index_for_lookup(normalized.year, normalized.index_file, config)
        result = _lookup_interface(source.index, normalized.interface)
        source.annotate(result)
        return {
            "status": "success",
            "message": (
                f"{result.method_count} methods, {result.property_count} properties"
                if result.found
                else "Interface not found in the indexed documentation"
            ),
            **source.payload(),
            "result": result.model_dump(exclude_unset=True),
            "execution_time": time.time() - start_time,
        }

    @mcp.tool()
    async def find_related_api_members(
        input_data: FindRelatedApiInput | None = None,
    ) -> dict[str, Any]:
        """Find SolidWorks API members related to an interface or member name.

        For an interface: its own members. For a member: the other members
        of every interface that also has it (often used together), plus
        members whose names contain it. Use it to explore around a call you
        know, such as what sits beside InsertSketch.

        Setup: none. SolidWorks must be installed, not running; it is never
        contacted. Read-only. The first call builds the index (about a
        second) and later calls reuse it. ``index_status`` is ``ready``
        (saved index), ``rebuilt`` (built for this call) or ``unavailable``
        (no index could be built).

        Returns ``result.related``: each member's interface, name, type and
        why it is related. ``result.found`` false means nothing matched, or
        no index could be built, in which case ``result.note`` says why.

        Example input: ``{"name": "InsertSketch", "max_results": 10}``

        Args:
            input_data (FindRelatedApiInput | None): What to explore.
                `name` (an interface or member) is required; `max_results`
                and `year` have defaults.

        Returns:
            dict[str, Any]: ``result``, ``year``, ``type_library_version``,
            ``index_status`` and ``source_index_file``, plus
            ``status``/``message``/``execution_time``.
        """
        start_time = time.time()
        normalized = normalize_input(input_data, FindRelatedApiInput)
        source = _index_for_lookup(normalized.year, normalized.index_file, config)
        result = _find_related_api_members(
            source.index, normalized.name, normalized.max_results
        )
        source.annotate(result)
        return {
            "status": "success",
            "message": (
                f"{len(result.related)} related member(s)"
                if result.found
                else "No related members found"
            ),
            **source.payload(),
            "result": result.model_dump(exclude_unset=True),
            "execution_time": time.time() - start_time,
        }

    # discover_solidworks_docs, search_solidworks_api_help, lookup_api_method,
    # lookup_api_interface, find_related_api_members
    tool_count = 5
    return tool_count
