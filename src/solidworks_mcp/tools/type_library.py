"""Read the registered SolidWorks type library into the docs index.

SolidWorks registers its type library (``sldworks.tlb``) under one GUID, with
one registry key per installed version. Reading it needs SolidWorks
installed, not running, and never touches the application: no SolidWorks
object is created or called, so the COM threading rules for the adapter do
not apply here.

The walk over the library is pure over a small part of the ``ITypeLib`` /
``ITypeInfo`` interface (:class:`TypeLibLike`, :class:`TypeInfoLike`), so
tests drive it with a fake library. Its records are Pydantic models, saved
into the index with ``model_dump()``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .tool_boundary import ToolOperationError

try:
    import pythoncom
except ImportError:
    pythoncom = None

try:
    import winreg
except ImportError:
    winreg = None

SOLIDWORKS_TYPELIB_GUID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
# Type library major version 34 is SolidWorks 2026.
_YEAR_OFFSET = 1992
# SolidWorks' first release. A lower version key (installs can leave a
# "1.0", which would read as 1993) isn't a SolidWorks release.
_FIRST_RELEASE_YEAR = 1995

_TKIND_DISPATCH = 4
_INVOKE_FUNC = 1
_INVOKE_PROPERTYGET = 2
_PARAMFLAG_FIN = 1
_PARAMFLAG_FOUT = 2
_VT_VOID = 24
_VT_HRESULT = 25
_VT_PTR = 26
_VT_USERDEFINED = 29

# IUnknown / IDispatch members every dual interface repeats.
_PLUMBING = frozenset(
    {
        "QueryInterface",
        "AddRef",
        "Release",
        "GetTypeInfoCount",
        "GetTypeInfo",
        "GetIDsOfNames",
        "Invoke",
    }
)

# VARTYPE -> the name SolidWorks' VBA help uses for it.
_VBA_TYPES = {
    2: "Integer",
    3: "Long",
    4: "Single",
    5: "Double",
    6: "Currency",
    7: "Date",
    8: "String",
    9: "Object",
    11: "Boolean",
    12: "Variant",
    13: "Object",
    16: "Byte",
    17: "Byte",
    18: "Integer",
    19: "Long",
    20: "LongLong",
    21: "LongLong",
    22: "Long",
    23: "Long",
}

_NEEDS_WINDOWS = (
    "The SolidWorks API index is read from SolidWorks' type library, "
    "which needs Windows with pywin32 and SolidWorks installed."
)

Direction = Literal["in", "out", "in_out"]
Access = Literal["read", "write", "read_write"]


class TypeInfoLike(Protocol):
    """The part of ``ITypeInfo`` the reader uses."""

    def GetTypeAttr(self) -> Any:
        """The interface's TYPEATTR; the reader uses ``cFuncs``."""

    def GetFuncDesc(self, index: int, /) -> Any:
        """The FUNCDESC of the function at ``index``."""

    def GetNames(self, memid: int, /) -> Sequence[str]:
        """The member name, then its parameter names."""

    def GetDocumentation(self, memid: int, /) -> Sequence[Any]:
        """``(name, help string, ...)``; ``memid`` -1 is the interface."""

    def GetRefTypeInfo(self, href: int, /) -> TypeInfoLike:
        """The type a user-defined type reference points at."""


class TypeLibLike(Protocol):
    """The part of ``ITypeLib`` the reader uses."""

    def GetTypeInfoCount(self) -> int:
        """How many types the library holds."""

    def GetTypeInfoType(self, index: int, /) -> int:
        """The TYPEKIND of the type at ``index``."""

    def GetDocumentation(self, index: int, /) -> Sequence[Any]:
        """``(name, help string, ...)`` of the type at ``index``."""

    def GetTypeInfo(self, index: int, /) -> TypeInfoLike:
        """The ITypeInfo of the type at ``index``."""


class TypeLibraryUnavailable(ToolOperationError):
    """No SolidWorks type library could be loaded; the message says why."""


class TypeLibraryInfo(BaseModel):
    """Which type library an index was built from.

    Attributes:
        guid (str): The SolidWorks type library GUID.
        version (str): The type library version, e.g. ``"34.0"``.
        year (int): The SolidWorks year that version belongs to.
        path (str): The ``.tlb`` file that was loaded.
    """

    model_config = ConfigDict(frozen=True)

    guid: str = Field(description="The SolidWorks type library GUID")
    version: str = Field(description="Type library version, e.g. '34.0'")
    year: int = Field(description="The SolidWorks release year, e.g. 2026")
    path: str = Field(description="The sldworks.tlb file that was read")


class ApiParameter(BaseModel):
    """One parameter of a SolidWorks API method.

    Attributes:
        name (str): The parameter name as the type library spells it.
        type (str): Its VBA type or interface name.
        direction (Direction): Whether the caller passes it, SolidWorks
            fills it, or both.
    """

    name: str = Field(description="Parameter name as the type library spells it")
    type: str = Field(
        description=(
            "VBA type (Long, String, Double, Boolean...) or an interface name "
            "such as IModelDoc2; Variant when the library's type has no VBA name"
        )
    )
    direction: Direction = Field(
        description=(
            "in: the caller passes it; out: SolidWorks fills it; in_out: both, "
            "so pass a variable by reference"
        )
    )


class ApiMethod(BaseModel):
    """A SolidWorks API method and its signature.

    Attributes:
        kind (Literal["method"]): Always ``method``.
        description (str): The library's one-line help string.
        parameters (list[ApiParameter]): The parameters, in call order.
        return_type (str | None): What it returns; None for nothing.
    """

    kind: Literal["method"] = "method"
    description: str = Field(default="", description="One-line help string")
    parameters: list[ApiParameter] = Field(
        default_factory=list, description="Parameters, in call order"
    )
    return_type: str | None = Field(
        default=None, description="Returned type; null when it returns nothing"
    )


class ApiProperty(BaseModel):
    """A SolidWorks API property.

    Attributes:
        kind (Literal["property"]): Always ``property``.
        description (str): The library's one-line help string.
        type (str | None): The value's type.
        access (Access): Whether it can be read, written or both.
    """

    kind: Literal["property"] = "property"
    description: str = Field(default="", description="One-line help string")
    type: str | None = Field(default=None, description="The value's type")
    access: Access = Field(description="read, write or read_write")


#: A member record, told apart by its ``kind``.
ApiMember = Annotated[ApiMethod | ApiProperty, Field(discriminator="kind")]


class ApiInterface(BaseModel):
    """One SolidWorks dispatch interface in the index.

    Attributes:
        methods (list[str]): Method names, sorted.
        properties (list[str]): Property names, sorted.
        method_count (int): How many methods.
        property_count (int): How many properties.
        members (dict[str, ApiMember]): Name -> signature record.
    """

    methods: list[str] = Field(description="Method names, sorted")
    properties: list[str] = Field(description="Property names, sorted")
    method_count: int = Field(description="Number of methods")
    property_count: int = Field(description="Number of properties")
    members: dict[str, ApiMember] = Field(
        description="Each member's signature record, by name"
    )


def year_of(major: int) -> int:
    """The SolidWorks year a type library major version belongs to.

    Args:
        major (int): The type library major version, e.g. 34.

    Returns:
        int: The release year, e.g. 2026.
    """
    return major + _YEAR_OFFSET


def _type_name(typedesc: Any, typeinfo: TypeInfoLike) -> str:
    """Name a parameter or return type the way the VBA help does.

    Args:
        typedesc (Any): A VARTYPE, or a ``(VT_PTR, inner)`` /
            ``(VT_USERDEFINED, href)`` tuple.
        typeinfo (TypeInfoLike): The interface the type appears on, to
            resolve user-defined types.

    Returns:
        str: ``Long``, ``String``, an interface name such as ``IModelDoc2``,
        or ``Variant`` for anything unmapped.
    """
    if isinstance(typedesc, tuple):
        kind, inner = typedesc[0], typedesc[1]
        if kind == _VT_PTR:
            return _type_name(inner, typeinfo)
        if kind == _VT_USERDEFINED:
            return str(typeinfo.GetRefTypeInfo(inner).GetDocumentation(-1)[0])
        typedesc = kind
    return _VBA_TYPES.get(typedesc, "Variant")


def _return_type(funcdesc: Any, typeinfo: TypeInfoLike) -> str | None:
    """The member's return type.

    Args:
        funcdesc (Any): The member's FUNCDESC.
        typeinfo (TypeInfoLike): The interface, to resolve user-defined types.

    Returns:
        str | None: The type name, or None when it returns nothing.
    """
    typedesc = funcdesc.rettype[0]
    if typedesc in (_VT_VOID, _VT_HRESULT):
        return None
    return _type_name(typedesc, typeinfo)


def _direction(paramflags: int) -> Direction:
    """A parameter's direction from its PARAMFLAG bits.

    Args:
        paramflags (int): ``PARAMFLAG_FIN`` (1) and/or ``PARAMFLAG_FOUT`` (2).

    Returns:
        Direction: ``in_out`` for both bits, ``out`` for FOUT alone,
        otherwise ``in``.
    """
    is_out = bool(paramflags & _PARAMFLAG_FOUT)
    if is_out and paramflags & _PARAMFLAG_FIN:
        return "in_out"
    return "out" if is_out else "in"


def _parameters(
    funcdesc: Any, names: Sequence[str], typeinfo: TypeInfoLike
) -> list[ApiParameter]:
    """Each parameter's name, type and direction.

    Args:
        funcdesc (Any): The member's FUNCDESC.
        names (Sequence[str]): ``GetNames`` output, member name first.
        typeinfo (TypeInfoLike): The interface, to resolve user-defined types.

    Returns:
        list[ApiParameter]: One record per parameter, in order.
    """
    params = []
    for position, (typedesc, paramflags, *_default) in enumerate(funcdesc.args):
        # A property setter's value argument has no name in the library.
        name = names[position + 1] if position + 1 < len(names) else "Value"
        params.append(
            ApiParameter(
                name=name,
                type=_type_name(typedesc, typeinfo),
                direction=_direction(paramflags),
            )
        )
    return params


def _add_property(
    members: dict[str, ApiMethod | ApiProperty],
    name: str,
    funcdesc: Any,
    description: str,
    typeinfo: TypeInfoLike,
) -> None:
    """Merge one property get/put/putref function into its property record.

    Args:
        members (dict[str, ApiMethod | ApiProperty]): The interface's records
            so far; updated in place.
        name (str): The property name.
        funcdesc (Any): This accessor's FUNCDESC.
        description (str): This accessor's help string.
        typeinfo (TypeInfoLike): The interface, to resolve user-defined types.
    """
    existing = members.get(name)
    if isinstance(existing, ApiMethod):
        return
    access: Access
    if funcdesc.invkind == _INVOKE_PROPERTYGET:
        access, value_type = "read", _return_type(funcdesc, typeinfo)
    else:
        access = "write"
        value_type = _type_name(funcdesc.args[-1][0], typeinfo)
    if existing is None:
        members[name] = ApiProperty(
            description=description, type=value_type, access=access
        )
        return
    if existing.access != access:
        existing.access = "read_write"
    # The getter's type is the one a caller reads back.
    if access == "read":
        existing.type = value_type
    existing.description = existing.description or description


def _interface_record(typeinfo: TypeInfoLike) -> ApiInterface:
    """Index one dispatch interface: name lists plus a record per member.

    Args:
        typeinfo (TypeInfoLike): The interface's ITypeInfo.

    Returns:
        ApiInterface: Its sorted name lists, counts and member records.
    """
    members: dict[str, ApiMethod | ApiProperty] = {}
    for position in range(typeinfo.GetTypeAttr().cFuncs):
        funcdesc = typeinfo.GetFuncDesc(position)
        names = typeinfo.GetNames(funcdesc.memid)
        name = names[0]
        if name in _PLUMBING or name.startswith("_"):
            continue
        description = typeinfo.GetDocumentation(funcdesc.memid)[1] or ""
        if funcdesc.invkind == _INVOKE_FUNC:
            # A name that is both a method and a property is kept as a method.
            members[name] = ApiMethod(
                description=description,
                parameters=_parameters(funcdesc, names, typeinfo),
                return_type=_return_type(funcdesc, typeinfo),
            )
        else:
            _add_property(members, name, funcdesc, description, typeinfo)
    methods = sorted(n for n, m in members.items() if isinstance(m, ApiMethod))
    properties = sorted(n for n, m in members.items() if isinstance(m, ApiProperty))
    return ApiInterface(
        methods=methods,
        properties=properties,
        method_count=len(methods),
        property_count=len(properties),
        members=members,
    )


def index_type_library(lib: TypeLibLike) -> dict[str, ApiInterface]:
    """Index every dispatch interface in a type library.

    Args:
        lib (TypeLibLike): An ITypeLib (or a fake with the same methods).

    Returns:
        dict[str, ApiInterface]: Interface name -> its record.
    """
    com_objects = {}
    for position in range(lib.GetTypeInfoCount()):
        if lib.GetTypeInfoType(position) != _TKIND_DISPATCH:
            continue
        name = lib.GetDocumentation(position)[0]
        com_objects[name] = _interface_record(lib.GetTypeInfo(position))
    return com_objects


def registered_versions(registry: Any) -> list[tuple[int, int]]:
    """Every registered SolidWorks type library version.

    Args:
        registry (Any): The ``winreg`` module (or a fake).

    Returns:
        list[tuple[int, int]]: ``(major, minor)`` pairs of SolidWorks
        releases; empty when none are registered. Keys older than the first
        release are left out.
    """
    try:
        key = registry.OpenKey(
            registry.HKEY_CLASSES_ROOT, rf"TypeLib\{SOLIDWORKS_TYPELIB_GUID}"
        )
    except OSError:
        return []
    versions = []
    with key:
        for position in range(registry.QueryInfoKey(key)[0]):
            # Registry version keys are hex: "22.0" is version 34.
            major, _, minor = registry.EnumKey(key, position).partition(".")
            try:
                version = (int(major, 16), int(minor or "0", 16))
            except ValueError:
                continue
            if year_of(version[0]) >= _FIRST_RELEASE_YEAR:
                versions.append(version)
    return versions


def choose_version(
    registered: list[tuple[int, int]], year: int | None, strict: bool
) -> tuple[int, int]:
    """Pick the type library version for a SolidWorks year.

    Args:
        registered (list[tuple[int, int]]): The registered versions.
        year (int | None): The wanted SolidWorks year, if any.
        strict (bool): True when the caller asked for this year, so a
            missing year is an error instead of falling back to the newest.

    Returns:
        tuple[int, int]: The chosen ``(major, minor)``.

    Raises:
        TypeLibraryUnavailable: Nothing is registered, or a strictly
            requested year isn't.
    """
    if not registered:
        raise TypeLibraryUnavailable(
            "No SolidWorks type library is registered on this machine, so the "
            "API index can't be built; it needs SolidWorks installed here."
        )
    if year:
        matching = [v for v in registered if year_of(v[0]) == year]
        if matching:
            return max(matching)
        if strict:
            installed = ", ".join(
                str(year_of(major)) for major, _ in sorted(set(registered))
            )
            raise TypeLibraryUnavailable(
                f"SolidWorks {year} isn't installed here; installed: {installed}."
            )
    return max(registered)


def target_version(
    year: int | None = None, strict: bool = False, registry: Any = None
) -> tuple[int, int]:
    """The type library version a load for ``year`` would read, without loading it.

    Lookups use this to find the saved index for that version before
    deciding whether to build one.

    Args:
        year (int | None): The wanted SolidWorks year; None for the newest.
        strict (bool): True to fail when that year isn't installed.
        registry (Any): The ``winreg`` module; defaults to the real one.

    Returns:
        tuple[int, int]: The ``(major, minor)`` version.

    Raises:
        TypeLibraryUnavailable: Not on Windows, or no matching type library
            is registered.
    """
    registry = registry if registry is not None else winreg
    if registry is None:
        raise TypeLibraryUnavailable(_NEEDS_WINDOWS)
    return choose_version(registered_versions(registry), year, strict)


def load_type_library(
    year: int | None = None,
    strict: bool = False,
    com: Any = None,
    registry: Any = None,
) -> tuple[Any, TypeLibraryInfo]:
    """Load the registered SolidWorks type library for a year.

    Args:
        year (int | None): The wanted SolidWorks year; None for the newest.
        strict (bool): True to fail when that year isn't installed.
        com (Any): The ``pythoncom`` module; defaults to the real one.
        registry (Any): The ``winreg`` module; defaults to the real one.

    Returns:
        tuple[Any, TypeLibraryInfo]: The ITypeLib and where it came from.

    Raises:
        TypeLibraryUnavailable: Not on Windows with pywin32, no matching
            type library is registered, or the registered one won't load.
    """
    com = com if com is not None else pythoncom
    if com is None:
        raise TypeLibraryUnavailable(_NEEDS_WINDOWS)
    major, minor = target_version(year, strict, registry)
    try:
        lib = com.LoadRegTypeLib(SOLIDWORKS_TYPELIB_GUID, major, minor)
    except com.com_error as exc:
        # An uninstall can leave the registry key behind its deleted .tlb.
        raise TypeLibraryUnavailable(
            f"SolidWorks {year_of(major)}'s type library is registered but "
            f"couldn't be loaded ({exc}); repairing that SolidWorks install "
            "restores it."
        ) from exc
    info = TypeLibraryInfo(
        guid=SOLIDWORKS_TYPELIB_GUID,
        version=f"{major}.{minor}",
        year=year_of(major),
        path=str(com.QueryPathOfRegTypeLib(SOLIDWORKS_TYPELIB_GUID, major, minor)),
    )
    return lib, info
