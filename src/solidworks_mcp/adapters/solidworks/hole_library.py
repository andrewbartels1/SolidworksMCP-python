"""The Hole Wizard library: standards, hole types and sizes, read from a file.

SolidWorks keeps the Hole Wizard's hole types and sizes in the Toolbox
library, ``swbrowser.sldedb``, a SQLite file. This module reads it read-only
(no COM, no SolidWorks needed) so ``list_hole_sizes`` can show what exists and
``create_hole`` can refuse a size that doesn't, before asking SolidWorks.

Per standard prefix (``ISO``, ``AI`` = ANSI inch, ``AM`` = ANSI metric,
``DIN``, ``JIS``) the library has two type tables, ``<P>_Type_Holes`` (simple
and tapped holes) and ``<P>_TYPE_BS`` (bolts and screws, which counterbores
and countersinks are sized for). Each row names a hole type, its
``HoleWizard5`` fastener index (``SWconst_Enum_Value``), the size table it
reads (``DataTable``: ``+DATA_HW_DrillSizes`` is ``<P>_DATA_HW_DrillSizes``)
and a bit mask of the hole kinds it serves (``ValidHoleTypes``). Size tables
have ``SIZE``, ``enabled`` and dimension columns that vary by table.

:class:`HoleLibrary` holds the rules; :class:`SqliteHoleLibrary` reads the
file and :class:`MemoryHoleLibrary` serves the mock adapter and tests.
"""

from __future__ import annotations

import os
import re
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, MetaData, Table, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool
from sqlmodel import create_engine, select

from ...exceptions import InputRefused

#: Our standard names -> the library's table prefix.
STANDARD_PREFIXES: dict[str, str] = {
    "iso": "ISO",
    "ansi_inch": "AI",
    "ansi_metric": "AM",
    "din": "DIN",
    "jis": "JIS",
}

#: Hole kind -> its bit in ``ValidHoleTypes``.
HOLE_KIND_BITS: dict[str, int] = {
    "counterbore": 1,
    "countersink": 2,
    "simple": 4,
    "tapped": 8,
}

#: ``(kind, standard) -> (hole type name, HoleWizard5 fastener index)`` used
#: when no ``fastener`` is given. ``drill`` and ``clearance`` are the two
#: simple-hole choices (design decision 5). The indexes are the library's
#: own (SolidWorks 2026) and serve when the library can't be read.
DEFAULT_FASTENERS: dict[tuple[str, str], tuple[str, int]] = {
    ("drill", "iso"): ("Drill sizes", 143),
    ("clearance", "iso"): ("Screw Clearances", 144),
    ("counterbore", "iso"): ("Cap (4762)", 139),
    ("countersink", "iso"): ("CTSK Flat (7046-1)", 141),
    ("tapped", "iso"): ("Tapped hole", 147),
    ("drill", "ansi_inch"): ("All Drill sizes", 18),
    ("clearance", "ansi_inch"): ("Screw Clearances", 22),
    ("counterbore", "ansi_inch"): ("Cap", 9),
    ("countersink", "ansi_inch"): ("Flat Head (82)", 15),
    ("tapped", "ansi_inch"): ("Tapped hole", 27),
    ("drill", "ansi_metric"): ("Drill sizes", 39),
    ("clearance", "ansi_metric"): ("Screw Clearances", 40),
    ("counterbore", "ansi_metric"): ("Cap (B18.3.1M)", 33),
    ("countersink", "ansi_metric"): ("Flat Head (B18.6.7M)", 36),
    ("tapped", "ansi_metric"): ("Tapped hole", 43),
    ("drill", "din"): ("Drill sizes", 72),
    ("clearance", "din"): ("Screw Clearances", 73),
    ("counterbore", "din"): ("Cap (912)", 67),
    ("countersink", "din"): ("CTSK Flat (EN ISO 7046-1)", 69),
    ("tapped", "din"): ("Tapped hole", 76),
    ("drill", "jis"): ("Drill sizes", 160),
    ("clearance", "jis"): ("Screw Clearances", 161),
    ("counterbore", "jis"): ("Cap (1176)", 156),
    ("countersink", "jis"): ("Flat CTSK (1111p2)", 158),
    ("tapped", "jis"): ("Tapped hole", 164),
}

#: The setting that names the library file, ahead of every other place.
LIBRARY_SETTING = "SOLIDWORKS_MCP_HOLE_LIBRARY"
_FILE_NAME = "swbrowser.sldedb"
#: Size-table columns that are bookkeeping, not dimensions.
_NOT_DIMENSIONS = {"size", "enabled", "key", "name to match", "sortorder"}
_NEAREST = 5


class HoleLibraryError(Exception):
    """The library can't be found or read; the message says where it looked."""


class HoleSizeError(InputRefused):
    """A hole type or size the library doesn't have; names the nearest ones."""


@dataclass(frozen=True)
class HoleType:
    """One Hole Wizard hole type of a standard.

    Attributes:
        name: The library's name for it, e.g. "Screw Clearances".
        code: Its ``HoleWizard5`` fastener index.
        table: The size table it reads, without the prefix's ``+``.
    """

    name: str
    code: int
    table: str


@dataclass(frozen=True)
class ResolvedHole:
    """What ``create_hole`` asks SolidWorks for.

    Attributes:
        fastener: The hole type's name.
        code: Its ``HoleWizard5`` fastener index.
        size: The size exactly as the library writes it.
        warning: Set when the size couldn't be checked.
    """

    fastener: str
    code: int
    size: str
    warning: str | None = None


def size_number(size: str) -> float | None:
    """The number in a size, for ordering nearest sizes.

    ``M6`` -> 6, ``Ø6.6`` -> 6.6, ``#10`` -> 10, ``1/4`` -> 0.25,
    ``1-1/2`` -> 1.5, ``M6x1.0`` -> 6.

    Args:
        size: A size as written in a table or by a caller.

    Returns:
        The number, or ``None`` when the size holds none.
    """
    text = size.strip()
    mixed = re.search(r"(\d+)[\s-]+(\d+)/(\d+)", text)
    if mixed:
        whole, top, bottom = (int(g) for g in mixed.groups())
        return whole + top / bottom if bottom else None
    fraction = re.search(r"(\d+)/(\d+)", text)
    if fraction:
        top, bottom = (int(g) for g in fraction.groups())
        return top / bottom if bottom else None
    number = re.search(r"\d+(?:\.\d+)?", text)
    return float(number.group(0)) if number else None


def is_screw_size(size: str) -> bool:
    """Whether a simple hole's size names a screw (clearance), not a drill.

    ``M6`` (metric), ``#10`` and fractions such as ``1/4`` (inch) name
    screws; a bare diameter (``6``, ``Ø6``, ``6 mm``) names a drill.
    """
    text = size.strip()
    return bool(re.match(r"^(M\d|#\d)", text, re.IGNORECASE)) or "/" in text


def _bare_diameter(size: str) -> float | None:
    """The diameter a bare drill size gives (``6``, ``Ø6``, ``6.0 mm``)."""
    match = re.fullmatch(r"\s*Ø?\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*", size, re.IGNORECASE)
    return float(match.group(1)) if match else None


def nearest_sizes(sizes: list[str], size: str) -> list[str]:
    """Up to five sizes closest in number to ``size``, in table order.

    Args:
        sizes: The table's sizes, in its order.
        size: The size asked for.

    Returns:
        The nearest sizes; the first five when ``size`` holds no number.
    """
    wanted = size_number(size)
    if wanted is None:
        return sizes[:_NEAREST]
    scored = [
        (abs(number - wanted), index)
        for index, entry in enumerate(sizes)
        if (number := size_number(entry)) is not None
    ]
    keep = {index for _, index in sorted(scored)[:_NEAREST]}
    return [entry for index, entry in enumerate(sizes) if index in keep] or sizes[
        :_NEAREST
    ]


class HoleLibrary(ABC):
    """The rules over a library's rows; subclasses supply the rows.

    A row of a type table is ``{"name", "code", "valid", "enabled", "table"}``;
    a size row is ``{"size", "enabled", "dimensions"}``.
    """

    @abstractmethod
    def type_rows(self, standard: str) -> list[dict[str, Any]]:
        """Every type row of a standard (both tables)."""

    @abstractmethod
    def size_rows(self, standard: str, table: str) -> list[dict[str, Any]]:
        """Every row of one of a standard's size tables."""

    def hole_types(self, standard: str, hole_type: str) -> list[HoleType]:
        """The enabled Hole Wizard types serving ``hole_type``, library order.

        A row whose index is 0 or -1 isn't a Hole Wizard type. Names can
        repeat (JIS); the first row with a real index wins.
        """
        bit = HOLE_KIND_BITS[hole_type]
        found: dict[str, HoleType] = {}
        for row in self.type_rows(standard):
            if not row["enabled"] or not int(row["valid"] or 0) & bit:
                continue
            if int(row["code"] or 0) <= 0 or row["name"] in found:
                continue
            table = str(row["table"] or "").lstrip("+")
            if table:
                found[row["name"]] = HoleType(row["name"], int(row["code"]), table)
        return list(found.values())

    def find_type(self, standard: str, hole_type: str, fastener: str) -> HoleType:
        """The hole type named ``fastener`` (case and spacing ignored).

        Raises:
            HoleSizeError: When the standard has no such type for the kind.
        """
        types = self.hole_types(standard, hole_type)
        key = _fold(fastener)
        for entry in types:
            if _fold(entry.name) == key:
                return entry
        names = ", ".join(f'"{t.name}"' for t in types)
        raise HoleSizeError(
            f'No {hole_type} hole type "{fastener}" in {standard}; it has {names}.'
        )

    def sizes(self, standard: str, entry: HoleType) -> list[str]:
        """The enabled sizes of a hole type, in the table's order."""
        return [
            str(row["size"])
            for row in self.size_rows(standard, entry.table)
            if row["enabled"] and str(row["size"] or "").strip()
        ]

    def match_size(self, standard: str, entry: HoleType, size: str) -> str:
        """The table's spelling of ``size``.

        Exact (case and spaces ignored) first; then, for a bare diameter, the
        size with the same number (``6`` -> ``Ø6.0``); then a size with its
        pitch (``M6x1.0``) as the table's row for ``M6`` when that row's pitch
        is the one given (the ISO tables list coarse threads without it).

        Raises:
            HoleSizeError: When the type has no such size; names the nearest.
        """
        sizes = self.sizes(standard, entry)
        key = _fold(size)
        for candidate in sizes:
            if _fold(candidate) == key:
                return candidate
        diameter = _bare_diameter(size)
        if diameter is not None:
            for candidate in sizes:
                if _bare_diameter(candidate) == diameter:
                    return candidate
        pitched = re.fullmatch(r"\s*(.+?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*", size)
        if pitched:
            base, pitch = _fold(pitched.group(1)), float(pitched.group(2))
            for row in self.size_rows(standard, entry.table):
                if (
                    row["enabled"]
                    and _fold(str(row["size"])) == base
                    and row["dimensions"].get("pitch") == pitch
                ):
                    return str(row["size"])
        nearest = ", ".join(nearest_sizes(sizes, size))
        raise HoleSizeError(
            f'"{entry.name}" ({standard}) has no size "{size}"; nearest: {nearest}.'
        )

    def dimensions(self, standard: str, entry: HoleType, size: str) -> dict[str, Any]:
        """One size's dimensions as the library stores them.

        Raises:
            HoleSizeError: When the type has no such size.
        """
        spelled = self.match_size(standard, entry, size)
        row = next(
            row
            for row in self.size_rows(standard, entry.table)
            if row["enabled"] and str(row["size"]) == spelled
        )
        return {"size": spelled, **row["dimensions"]}

    def resolve(
        self, standard: str, hole_type: str, size: str, fastener: str | None
    ) -> ResolvedHole:
        """The hole type, index and size ``create_hole`` asks SolidWorks for.

        With no ``fastener``, a simple hole uses "Screw Clearances" for a
        screw size and the drill table for a bare diameter; the other kinds
        use :data:`DEFAULT_FASTENERS`.

        Raises:
            HoleSizeError: For an unknown hole type or size.
        """
        name = fastener or default_fastener(standard, hole_type, size)[0]
        entry = self.find_type(standard, hole_type, name)
        return ResolvedHole(
            entry.name, entry.code, self.match_size(standard, entry, size)
        )


def default_fastener(standard: str, hole_type: str, size: str) -> tuple[str, int]:
    """The default hole type's name and index for a kind and size."""
    kind = hole_type
    if hole_type == "simple":
        kind = "clearance" if is_screw_size(size) else "drill"
    return DEFAULT_FASTENERS[(kind, standard)]


def unchecked(
    standard: str, hole_type: str, size: str, fastener: str | None, reason: str
) -> ResolvedHole:
    """The defaults to try when the library can't be read, with a warning.

    A named ``fastener`` is used only when it is the default for the kind,
    as its index is otherwise unknown.

    Raises:
        HoleSizeError: For a ``fastener`` whose index can't be known.
    """
    name, code = default_fastener(standard, hole_type, size)
    if fastener and _fold(fastener) != _fold(name):
        raise HoleSizeError(
            f'The hole type "{fastener}" can\'t be used: {reason} Leave '
            f'`fastener` out to use "{name}".'
        )
    diameter = _bare_diameter(size)
    spelled = (
        f"Ø{diameter:.1f}" if diameter is not None and standard != "ansi_inch" else size
    )
    return ResolvedHole(
        name,
        code,
        spelled,
        f"The size wasn't checked: {reason} The hole was attempted as "
        f'"{name}" {spelled}.',
    )


def _fold(text: str) -> str:
    """Text compared without case or spaces."""
    return re.sub(r"\s+", "", text).casefold()


class MemoryHoleLibrary(HoleLibrary):
    """A library held in memory: the mock adapter's and the tests'.

    Args:
        types: ``standard -> type rows``.
        sizes: ``(standard, table) -> size rows``.
    """

    def __init__(
        self,
        types: dict[str, list[dict[str, Any]]],
        sizes: dict[tuple[str, str], list[dict[str, Any]]],
    ) -> None:
        self._types = types
        self._sizes = sizes

    def type_rows(self, standard: str) -> list[dict[str, Any]]:
        """The standard's type rows (none for one it doesn't hold)."""
        return self._types.get(standard, [])

    def size_rows(self, standard: str, table: str) -> list[dict[str, Any]]:
        """The size rows of one table (none for one it doesn't hold)."""
        return self._sizes.get((standard, table), [])


class SqliteHoleLibrary(HoleLibrary):
    """The installed library, read read-only and immutable.

    Table names come from the library's own rows; each is checked against
    the file's own table list and reflected, never taken from a caller, and
    rows are read with SQLModel's ``select()``: no SQL is built as text.
    Rows are read once per table, and the file is closed after each read, so
    SolidWorks (or Toolbox Settings) can always replace it.

    Args:
        path: The ``swbrowser.sldedb`` file.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._tables: dict[str, str] | None = None
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def _engine(self) -> Engine:
        """A read-only engine on the file: no lock taken, nothing written.

        ``immutable=1`` lets the file be read while SolidWorks has it open;
        ``NullPool`` closes each connection when its ``with`` block ends, so
        the file is never held open between reads.
        """
        uri = f"{self.path.resolve().as_uri()}?mode=ro&immutable=1"
        return create_engine(
            "sqlite://",
            creator=lambda: sqlite3.connect(uri, uri=True),
            poolclass=NullPool,
        )

    def _rows(self, table: str) -> list[dict[str, Any]]:
        """Every row of a table, columns keyed by their lower-case name.

        No SQL is written as text: the table is reflected from the file
        (named only if the file's own table list has it) and read with
        ``select()``, so SQLAlchemy quotes every identifier.

        Raises:
            HoleLibraryError: When the file can't be read or lacks the table.
        """
        if table.lower() in self._cache:
            return self._cache[table.lower()]
        engine = self._engine()
        try:
            with engine.connect() as connection:
                if self._tables is None:
                    self._tables = {
                        name.lower(): name
                        for name in inspect(connection).get_table_names()
                    }
                real = self._tables.get(table.lower())
                if real is None:
                    raise HoleLibraryError(
                        f"The Hole Wizard library {self.path} has no table {table}."
                    )
                reflected = Table(real, MetaData(), autoload_with=connection)
                rows = [
                    {str(key).lower(): value for key, value in row.items()}
                    for row in connection.execute(select(reflected)).mappings()
                ]
        except SQLAlchemyError as exc:
            raise HoleLibraryError(
                f"The Hole Wizard library {self.path} couldn't be read: {exc}."
            ) from exc
        finally:
            engine.dispose()
        self._cache[table.lower()] = rows
        return rows

    def type_rows(self, standard: str) -> list[dict[str, Any]]:
        """Both type tables of a standard, holes first."""
        prefix = STANDARD_PREFIXES[standard]
        rows = []
        for table in (f"{prefix}_Type_Holes", f"{prefix}_TYPE_BS"):
            for row in self._rows(table):
                rows.append(
                    {
                        "name": row.get("name"),
                        "code": row.get("swconst_enum_value"),
                        "valid": row.get("validholetypes"),
                        "enabled": row.get("enabled"),
                        "table": row.get("datatable"),
                    }
                )
        return rows

    def size_rows(self, standard: str, table: str) -> list[dict[str, Any]]:
        """One size table's rows, its dimension columns as numbers."""
        rows = self._rows(f"{STANDARD_PREFIXES[standard]}_{table}")
        return [
            {
                "size": row.get("size"),
                "enabled": row.get("enabled"),
                "dimensions": {
                    key: _number(value)
                    for key, value in row.items()
                    if key not in _NOT_DIMENSIONS
                },
            }
            for row in rows
        ]


def _number(value: Any) -> Any:
    """A stored dimension as a float when it reads as one."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


_LOADED: dict[tuple[str, float], SqliteHoleLibrary] = {}


def load(path: Path) -> SqliteHoleLibrary:
    """The library at ``path``, one per path and modification time."""
    key = (str(path), path.stat().st_mtime)
    if key not in _LOADED:
        _LOADED[key] = SqliteHoleLibrary(path)
    return _LOADED[key]


def candidate_paths() -> list[Path]:
    """Where the library may be, first hit wins (design decision 3).

    The ``SOLIDWORKS_MCP_HOLE_LIBRARY`` setting; then, for each installed
    SolidWorks year (newest first), the Toolbox data folder from the
    registry (HKCU, then HKLM) with each ``lang`` folder, English first;
    then the install folder's template.
    """
    paths: list[Path] = []
    setting = os.getenv(LIBRARY_SETTING, "").strip()
    if setting:
        paths.append(Path(setting))
    for year in _registry_years():
        key = rf"Software\SolidWorks\{year}"
        for hive in ("HKCU", "HKLM"):
            data = _registry_value(hive, rf"{key}\General", "Toolbox Data Location")
            if data:
                paths.extend(_language_files(Path(data) / "lang"))
        install = _registry_value("HKLM", rf"{key}\Setup", "SolidWorks Folder")
        if install:
            paths.extend(
                _language_files(Path(install) / "Toolbox" / "data utilities" / "lang")
            )
    return list(dict.fromkeys(paths))


def _language_files(lang: Path) -> list[Path]:
    """``<lang>/<language>/swbrowser.sldedb`` for each language, English first."""
    languages = ["english"]
    if lang.is_dir():
        languages += sorted(
            p.name for p in lang.iterdir() if p.is_dir() and p.name.lower() != "english"
        )
    return [lang / name / _FILE_NAME for name in languages]


def find_library() -> SqliteHoleLibrary:
    """The installed library.

    Raises:
        HoleLibraryError: Naming every place looked and the setting.
    """
    tried = candidate_paths()
    for path in tried:
        if path.is_file():
            return load(path)
    where = "; ".join(str(p) for p in tried) or "no SolidWorks install in the registry"
    raise HoleLibraryError(
        f"No Hole Wizard library ({_FILE_NAME}) found. Looked in: {where}. "
        f"Set {LIBRARY_SETTING} to the file's path."
    )


def _registry_years() -> list[str]:
    """Installed ``SOLIDWORKS <year>`` registry keys, newest first."""
    names: set[str] = set()
    for hive in ("HKCU", "HKLM"):
        names.update(
            name
            for name in _registry_subkeys(hive, r"Software\SolidWorks")
            if re.fullmatch(r"SOLIDWORKS \d{4}", name, re.IGNORECASE)
        )
    return sorted(names, reverse=True)


def _registry_subkeys(hive: str, key: str) -> list[str]:
    """A registry key's subkey names; none off Windows or when it's missing."""
    try:
        import winreg

        root = winreg.HKEY_CURRENT_USER if hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        with winreg.OpenKey(root, key) as handle:
            count = winreg.QueryInfoKey(handle)[0]
            return [winreg.EnumKey(handle, i) for i in range(count)]
    except (ImportError, OSError):
        return []


def _registry_value(hive: str, key: str, name: str) -> str | None:
    """One registry string; ``None`` off Windows or when it's missing."""
    try:
        import winreg

        root = winreg.HKEY_CURRENT_USER if hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        with winreg.OpenKey(root, key) as handle:
            value, _ = winreg.QueryValueEx(handle, name)
            return str(value) if value else None
    except (ImportError, OSError):
        return None


def describe(
    library: HoleLibrary,
    standard: str,
    hole_type: str,
    fastener: str | None = None,
    size: str | None = None,
) -> dict[str, Any]:
    """What ``list_hole_sizes`` returns.

    No ``size``: the hole types of the kind (only ``fastener``'s when given),
    each with its enabled sizes. With ``size``: that size's dimensions, in
    the hole type ``fastener`` names or the default one for the kind.

    Raises:
        HoleSizeError: For an unknown hole type or size.
    """
    if size is not None:
        name = fastener or default_fastener(standard, hole_type, size)[0]
        entry = library.find_type(standard, hole_type, name)
        return {
            "standard": standard,
            "hole_type": hole_type,
            "fastener": entry.name,
            "units": "in" if standard == "ansi_inch" else "mm",
            "dimensions": library.dimensions(standard, entry, size),
        }
    types = (
        [library.find_type(standard, hole_type, fastener)]
        if fastener
        else library.hole_types(standard, hole_type)
    )
    return {
        "standard": standard,
        "hole_type": hole_type,
        "units": "in" if standard == "ansi_inch" else "mm",
        "hole_types": [
            {"name": t.name, "sizes": library.sizes(standard, t)} for t in types
        ],
    }


def _sizes(table: list[tuple[str, dict[str, float]]]) -> list[dict[str, Any]]:
    """Size rows from ``(size, dimensions)`` pairs, all enabled."""
    return [{"size": s, "enabled": 1, "dimensions": d} for s, d in table]


def _metric(
    column: str, values: dict[str, float]
) -> list[tuple[str, dict[str, float]]]:
    """``M<n>`` rows with a diameter and one more column."""
    return [(f"M{n:g}", {"diameter": n, column: v}) for n, v in values.items()]


def sample_library() -> MemoryHoleLibrary:
    """A few real ISO and ANSI inch hole types and sizes (SolidWorks 2026).

    The mock adapter's library: the default hole types of each kind, with
    their dimensions copied from the installed library.
    """
    iso_types = [
        ("Drill sizes", 143, 4, "+DATA_HW_DrillSizes"),
        ("Screw Clearances", 144, 4, "+DATA_HW_ScrewClearances"),
        ("Tapped hole", 147, 8, "+DATA_HW_TappedHole"),
        ("Cap (4762)", 139, 1, "+DATA_BS_SHCSCREW4762"),
        ("CTSK Flat (7046-1)", 141, 2, "+DATA_BS_CFHCRSCREW7046"),
    ]
    inch_types = [
        ("All Drill sizes", 18, 4, "+DATA_HW_AllDrillSizes"),
        ("Screw Clearances", 22, 4, "+DATA_HW_ScrewClearances"),
        ("Tapped hole", 27, 8, "+DATA_HW_TappedHole"),
        ("Cap", 9, 1, "+DATA_SHCSCREW"),
        ("Flat Head (82)", 15, 2, "+DATA_FHMS"),
    ]
    screws = [3, 4, 5, 6, 8, 10]
    cap = {3: (6.5, 3.4), 4: (8.0, 4.4), 5: (10.0, 5.4), 6: (11.0, 6.4)}
    cap |= {8: (15.0, 8.6), 10: (18.0, 10.6)}
    iso_sizes = {
        "DATA_HW_DrillSizes": [(f"Ø{n:.1f}", {"diameter": float(n)}) for n in screws],
        "DATA_HW_ScrewClearances": _metric(
            "normal_fit", {3: 3.4, 4: 4.5, 5: 5.5, 6: 6.6, 8: 9.0, 10: 11.0}
        ),
        "DATA_HW_TappedHole": [
            *_metric("pitch", {3: 0.5, 4: 0.7, 5: 0.8, 6: 1.0, 8: 1.25}),
            ("M8x1.0", {"diameter": 8.0, "pitch": 1.0}),
            ("M10", {"diameter": 10.0, "pitch": 1.5}),
        ],
        "DATA_BS_SHCSCREW4762": [
            (f"M{n}", {"diameter": float(n), "cbore_dia": d, "cbore_depth": h})
            for n, (d, h) in cap.items()
        ],
        "DATA_BS_CFHCRSCREW7046": _metric(
            "head_dia", {3: 6.3, 4: 9.4, 5: 10.4, 6: 12.6, 8: 17.3, 10: 20.0}
        ),
    }
    inch = {"#6": 0.138, "#8": 0.164, "#10": 0.19, "1/4": 0.25, "3/8": 0.375}
    inch_sizes = {
        "DATA_HW_AllDrillSizes": [
            ("#7", {"diameter": 0.201}),
            ("1/4", {"diameter": 0.25}),
            ("3/8", {"diameter": 0.375}),
        ],
        "DATA_HW_ScrewClearances": [
            (s, {"diameter": d, "normal_fit": f})
            for (s, d), f in zip(
                inch.items(), (0.17, 0.196, 0.221, 0.281, 0.406), strict=True
            )
        ],
        "DATA_HW_TappedHole": [
            ("#6-32", {"diameter": 0.138, "pitch": 32.0}),
            ("#8-32", {"diameter": 0.164, "pitch": 32.0}),
            ("#10-24", {"diameter": 0.19, "pitch": 24.0}),
            ("#10-32", {"diameter": 0.19, "pitch": 32.0}),
            ("1/4-20", {"diameter": 0.25, "pitch": 20.0}),
        ],
        "DATA_SHCSCREW": [
            (s, {"diameter": d, "cbore_dia": c, "cbore_depth": d})
            for (s, d), c in zip(
                inch.items(), (0.2813, 0.3125, 0.375, 0.4375, 0.625), strict=True
            )
        ],
        "DATA_FHMS": [
            (s, {"diameter": d, "head_dia": c})
            for (s, d), c in zip(
                inch.items(), (0.279, 0.332, 0.385, 0.507, 0.762), strict=True
            )
        ],
    }

    def rows(types: list[tuple[str, int, int, str]]) -> list[dict[str, Any]]:
        return [
            {"name": n, "code": c, "valid": v, "enabled": 1, "table": t}
            for n, c, v, t in types
        ]

    return MemoryHoleLibrary(
        {"iso": rows(iso_types), "ansi_inch": rows(inch_types)},
        {
            **{("iso", t): _sizes(r) for t, r in iso_sizes.items()},
            **{("ansi_inch", t): _sizes(r) for t, r in inch_sizes.items()},
        },
    )
