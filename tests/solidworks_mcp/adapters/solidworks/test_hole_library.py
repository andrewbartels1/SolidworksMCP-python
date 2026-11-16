"""The Hole Wizard library reader, against a small SQLite file built here."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.solidworks import hole_library as hl
from solidworks_mcp.adapters.solidworks.hole_library import (
    HoleLibraryError,
    HoleSizeError,
    HoleType,
    SqliteHoleLibrary,
)


def _library_file(path: Path) -> Path:
    """An ISO library: simple and tapped holes, a counterbore screw, quirks.

    Quirks: a disabled type, a type with index -1, a repeated name (the
    first row with a real index wins), a disabled size, and a type whose
    size table is missing.
    """
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(
            "CREATE TABLE ISO_Type_Holes (ID, enabled, Name, ValidHoleTypes, "
            "DataTable, SWconst_Enum_Value)"
        )
        db.executemany(
            "INSERT INTO ISO_Type_Holes VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, 1, "Drill sizes", 4, "+DATA_HW_DrillSizes", 143),
                (2, 1, "Screw Clearances", 4, "+DATA_HW_ScrewClearances", 144),
                (3, 1, "Tapped hole", 8, "+DATA_HW_TappedHole", 147),
                (4, 0, "Old drills", 4, "+DATA_HW_DrillSizes", 99),
                (5, 1, "Not a wizard type", 4, "+DATA_HW_DrillSizes", -1),
                (6, 1, "Missing table", 4, "+DATA_HW_Gone", 150),
                (7, 1, "No table", 4, "", 151),
            ],
        )
        db.execute(
            "CREATE TABLE ISO_TYPE_BS (ID, enabled, Name, ValidHoleTypes, "
            "DataTable, SWConst_Enum_Value)"
        )
        db.executemany(
            "INSERT INTO ISO_TYPE_BS VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, 1, "Cap (4762)", 1, "+DATA_BS_SHCSCREW4762", 0),
                (2, 1, "Cap (4762)", 1, "+DATA_BS_SHCSCREW4762", 139),
                (3, 1, "Cap (4762)", 1, "+DATA_BS_OTHER", 140),
            ],
        )
        db.execute(
            'CREATE TABLE ISO_DATA_HW_DrillSizes (SIZE, Diameter, enabled, key, "Name To Match")'
        )
        db.executemany(
            "INSERT INTO ISO_DATA_HW_DrillSizes VALUES (?, ?, ?, ?, ?)",
            [
                ("Ø5.0", "5", 1, 1, None),
                ("Ø6.0", "6", 1, 2, None),
                ("Ø6.5", "6.5", 0, 3, None),
                ("", "0", 1, 4, None),
            ],
        )
        db.execute(
            "CREATE TABLE ISO_DATA_HW_ScrewClearances (SIZE, NORMAL_FIT, enabled, key)"
        )
        db.executemany(
            "INSERT INTO ISO_DATA_HW_ScrewClearances VALUES (?, ?, ?, ?)",
            [("M5", "5.5", 1, 1), ("M6", "6.6", 1, 2), ("M8", "9", 1, 3)],
        )
        db.execute("CREATE TABLE ISO_DATA_HW_TappedHole (SIZE, Pitch, enabled, key)")
        db.executemany(
            "INSERT INTO ISO_DATA_HW_TappedHole VALUES (?, ?, ?, ?)",
            [("M6", "1", 1, 1), ("M8", "1.25", 1, 2), ("M8x1.0", "1", 1, 3)],
        )
        db.execute(
            "CREATE TABLE ISO_DATA_BS_SHCSCREW4762 (SIZE, CBORE_DIA, CBORE_DEPTH, "
            "THREAD, enabled, key)"
        )
        db.executemany(
            "INSERT INTO ISO_DATA_BS_SHCSCREW4762 VALUES (?, ?, ?, ?, ?, ?)",
            [("M6", "11", "6.4", "coarse", 1, 1), ("M8", "15", "8.6", None, 1, 2)],
        )
    return path


@pytest.fixture
def library(tmp_path: Path) -> SqliteHoleLibrary:
    return SqliteHoleLibrary(_library_file(tmp_path / "swbrowser.sldedb"))


def test_hole_types_skip_disabled_unindexed_and_repeated_rows(
    library: SqliteHoleLibrary,
) -> None:
    simple = library.hole_types("iso", "simple")
    assert [t.name for t in simple] == [
        "Drill sizes",
        "Screw Clearances",
        "Missing table",
    ]
    cbore = library.hole_types("iso", "counterbore")
    assert cbore == [HoleType("Cap (4762)", 139, "DATA_BS_SHCSCREW4762")]


def test_sizes_are_enabled_and_in_table_order(library: SqliteHoleLibrary) -> None:
    drills = library.find_type("iso", "simple", "drill SIZES")
    assert library.sizes("iso", drills) == ["Ø5.0", "Ø6.0"]


@pytest.mark.parametrize(
    ("hole_type", "size", "fastener", "expected"),
    [
        ("simple", "M6", None, ("Screw Clearances", 144, "M6")),
        ("simple", "6", None, ("Drill sizes", 143, "Ø6.0")),
        ("simple", "Ø6 mm", None, ("Drill sizes", 143, "Ø6.0")),
        ("simple", "m6", "Screw Clearances", ("Screw Clearances", 144, "M6")),
        ("tapped", "M6x1.0", None, ("Tapped hole", 147, "M6")),
        ("tapped", "M8x1.0", None, ("Tapped hole", 147, "M8x1.0")),
        ("counterbore", "M8", None, ("Cap (4762)", 139, "M8")),
    ],
)
def test_resolve(
    library: SqliteHoleLibrary,
    hole_type: str,
    size: str,
    fastener: str | None,
    expected: tuple[str, int, str],
) -> None:
    chosen = library.resolve("iso", hole_type, size, fastener)
    assert (chosen.fastener, chosen.code, chosen.size) == expected
    assert chosen.warning is None


def test_an_unknown_size_names_the_nearest(library: SqliteHoleLibrary) -> None:
    with pytest.raises(HoleSizeError, match=r'no size "M7"; nearest: M5, M6, M8'):
        library.resolve("iso", "simple", "M7", None)
    with pytest.raises(HoleSizeError, match="nearest: M6, M8"):
        library.resolve("iso", "tapped", "M6x0.5", None)


def test_an_unknown_hole_type_lists_the_types(library: SqliteHoleLibrary) -> None:
    with pytest.raises(HoleSizeError, match='"Drill sizes", "Screw Clearances"'):
        library.resolve("iso", "simple", "M6", "Dowel Holes")


def test_dimensions_are_numbers_where_they_read_as_one(
    library: SqliteHoleLibrary,
) -> None:
    cap = library.find_type("iso", "counterbore", "Cap (4762)")
    assert library.dimensions("iso", cap, "m6") == {
        "size": "M6",
        "cbore_dia": 11.0,
        "cbore_depth": 6.4,
        "thread": "coarse",
    }
    assert library.dimensions("iso", cap, "M8")["thread"] is None


def test_a_missing_table_or_a_bad_file_is_a_library_error(
    library: SqliteHoleLibrary, tmp_path: Path
) -> None:
    gone = library.find_type("iso", "simple", "Missing table")
    with pytest.raises(HoleLibraryError, match="has no table ISO_DATA_HW_Gone"):
        library.sizes("iso", gone)
    with pytest.raises(HoleLibraryError, match="has no table JIS_Type_Holes"):
        library.hole_types("jis", "simple")
    junk = tmp_path / "junk.sldedb"
    junk.write_text("not a database", encoding="utf-8")
    with pytest.raises(HoleLibraryError, match="couldn't be read"):
        SqliteHoleLibrary(junk).hole_types("iso", "simple")


def test_rows_are_read_once(library: SqliteHoleLibrary) -> None:
    first = library.type_rows("iso")
    library.path.unlink()
    assert library.type_rows("iso") == first


def test_describe_lists_types_one_type_or_one_size(library: SqliteHoleLibrary) -> None:
    clear = hl.describe(library, "iso", "simple", "Screw Clearances")
    assert clear == {
        "standard": "iso",
        "hole_type": "simple",
        "units": "mm",
        "hole_types": [{"name": "Screw Clearances", "sizes": ["M5", "M6", "M8"]}],
    }
    tapped = hl.describe(library, "iso", "tapped")
    assert tapped["hole_types"] == [
        {"name": "Tapped hole", "sizes": ["M6", "M8", "M8x1.0"]}
    ]
    one = hl.describe(library, "iso", "counterbore", size="M6")
    assert one["fastener"] == "Cap (4762)"
    assert one["dimensions"]["cbore_depth"] == 6.4


def test_describe_in_inches_for_ansi_inch() -> None:
    sample = hl.sample_library()
    assert hl.describe(sample, "ansi_inch", "tapped")["units"] == "in"
    assert hl.describe(sample, "ansi_inch", "simple", size="1/4")["fastener"] == (
        "Screw Clearances"
    )


@pytest.mark.parametrize(
    ("size", "number"),
    [
        ("M6", 6.0),
        ("Ø6.6", 6.6),
        ("#10", 10.0),
        ("1/4", 0.25),
        ("1-1/2", 1.5),
        ("1 1/2", 1.5),
        ("M6x1.0", 6.0),
        ("1/0", None),
        ("2-1/0", None),
        ("Letter A", None),
    ],
)
def test_size_number(size: str, number: float | None) -> None:
    assert hl.size_number(size) == number


@pytest.mark.parametrize(
    ("size", "screw"),
    [("M6", True), ("#10", True), ("1/4", True), ("6", False), ("Ø6", False)],
)
def test_is_screw_size(size: str, screw: bool) -> None:
    assert hl.is_screw_size(size) is screw


def test_nearest_sizes() -> None:
    sizes = ["Letter A", "M2", "M3", "M4", "M5", "M6", "M8", "M10"]
    assert hl.nearest_sizes(sizes, "M7") == ["M4", "M5", "M6", "M8", "M10"]
    assert hl.nearest_sizes(sizes, "Letter Z") == sizes[:5]
    assert hl.nearest_sizes(["Letter A", "Letter B"], "M7") == ["Letter A", "Letter B"]


def test_unchecked_uses_the_default_with_a_warning() -> None:
    drill = hl.unchecked("iso", "simple", "6", None, "No library.")
    assert (drill.fastener, drill.code, drill.size) == ("Drill sizes", 143, "Ø6.0")
    assert drill.warning == (
        "The size wasn't checked: No library. The hole was attempted as \"Drill "
        'sizes" Ø6.0.'
    )
    inch = hl.unchecked("ansi_inch", "counterbore", "#10", "cap", "No library.")
    assert (inch.fastener, inch.code, inch.size) == ("Cap", 9, "#10")
    with pytest.raises(
        HoleSizeError, match='Leave `fastener` out to use "Cap \\(912\\)"'
    ):
        hl.unchecked("din", "counterbore", "M6", "Pan (7045)", "No library.")


def test_the_mock_sample_covers_every_default_it_names() -> None:
    sample = hl.sample_library()
    for (kind, standard), (name, code) in hl.DEFAULT_FASTENERS.items():
        if standard not in ("iso", "ansi_inch"):
            continue
        hole_type = "simple" if kind in ("drill", "clearance") else kind
        entry = sample.find_type(standard, hole_type, name)
        assert entry.code == code
        assert sample.sizes(standard, entry)
    assert sample.size_rows("din", "DATA_HW_DrillSizes") == []


# ---- finding the file ------------------------------------------------------------


def test_the_setting_comes_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    file = _library_file(tmp_path / "mine.sldedb")
    monkeypatch.setenv(hl.LIBRARY_SETTING, str(file))
    monkeypatch.setattr(hl, "_registry_years", lambda: [])
    found = hl.find_library()
    assert found.path == file
    assert hl.find_library() is found  # cached by path and time


def test_registry_folders_are_searched_newest_year_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data = tmp_path / "data"
    (data / "lang" / "german").mkdir(parents=True)
    (data / "lang" / "english").mkdir()
    (data / "lang" / "notes.txt").write_text("", encoding="utf-8")
    install = tmp_path / "install"
    values = {
        ("HKCU", r"Software\SolidWorks\SOLIDWORKS 2026\General"): str(data),
        ("HKLM", r"Software\SolidWorks\SOLIDWORKS 2026\Setup"): str(install),
    }
    monkeypatch.delenv(hl.LIBRARY_SETTING, raising=False)
    monkeypatch.setattr(hl, "_registry_years", lambda: ["SOLIDWORKS 2026"])
    monkeypatch.setattr(hl, "_registry_value", lambda h, k, n: values.get((h, k)))
    template = install / "Toolbox" / "data utilities" / "lang"
    assert hl.candidate_paths() == [
        data / "lang" / "english" / "swbrowser.sldedb",
        data / "lang" / "german" / "swbrowser.sldedb",
        template / "english" / "swbrowser.sldedb",
    ]
    _library_file(data / "lang" / "german" / "swbrowser.sldedb")
    assert hl.find_library().path == data / "lang" / "german" / "swbrowser.sldedb"


def test_no_library_names_where_it_looked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(hl.LIBRARY_SETTING, str(tmp_path / "none.sldedb"))
    monkeypatch.setattr(hl, "_registry_years", lambda: [])
    with pytest.raises(HoleLibraryError, match=r"none\.sldedb\. Set SOLIDWORKS_MCP"):
        hl.find_library()
    monkeypatch.delenv(hl.LIBRARY_SETTING)
    with pytest.raises(HoleLibraryError, match="no SolidWorks install in the registry"):
        hl.find_library()


class _Key:
    """A fake open registry key."""

    def __init__(self, path: str) -> None:
        self.path = path

    def __enter__(self) -> _Key:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def _fake_winreg(tree: dict[str, Any]) -> SimpleNamespace:
    """A ``winreg`` stand-in over ``{"<hive>\\<key>": subkeys or values}``."""

    def open_key(root: str, key: str) -> _Key:
        path = f"{root}\\{key}"
        if path not in tree:
            raise OSError(path)
        return _Key(path)

    return SimpleNamespace(
        HKEY_CURRENT_USER="HKCU",
        HKEY_LOCAL_MACHINE="HKLM",
        OpenKey=open_key,
        QueryInfoKey=lambda key: (len(tree[key.path]),),
        EnumKey=lambda key, i: tree[key.path][i],
        QueryValueEx=lambda key, name: (tree[key.path].get(name), 1),
    )


def test_registry_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    tree = {
        r"HKCU\Software\SolidWorks": ["SOLIDWORKS 2025", "General", "SOLIDWORKS 2026"],
        r"HKLM\Software\SolidWorks": ["SOLIDWORKS 2026"],
        r"HKCU\Software\SolidWorks\SOLIDWORKS 2026\General": {
            "Toolbox Data Location": r"C:\Toolbox",
            "Empty": "",
        },
    }
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(tree))
    assert hl._registry_years() == ["SOLIDWORKS 2026", "SOLIDWORKS 2025"]
    key = r"Software\SolidWorks\SOLIDWORKS 2026\General"
    assert hl._registry_value("HKCU", key, "Toolbox Data Location") == r"C:\Toolbox"
    assert hl._registry_value("HKCU", key, "Empty") is None
    assert hl._registry_value("HKLM", key, "Toolbox Data Location") is None
    assert hl._registry_subkeys("HKLM", r"Software\Nothing") == []


def test_no_winreg_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "winreg", None)
    assert hl._registry_subkeys("HKCU", r"Software\SolidWorks") == []
    assert hl._registry_value("HKCU", r"Software\SolidWorks", "x") is None
