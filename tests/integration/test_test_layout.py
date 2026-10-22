"""Unit tests mirror ``src/``: every file under ``tests/solidworks_mcp`` maps to a module.

``src/solidworks_mcp/<path>/<module>.py`` is tested in
``tests/solidworks_mcp/<path>/test_<module>[_<topic>].py`` (a package's
``__init__.py`` in ``test_init.py``). Cross-module and end-to-end tests live in
``tests/integration/``; real-SolidWorks tests in ``tests/live/``.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "solidworks_mcp"
UNIT = REPO / "tests" / "solidworks_mcp"


def _mirrors_a_module(test_file: Path) -> bool:
    package = SRC / test_file.parent.relative_to(UNIT)
    name = test_file.stem.removeprefix("test_")
    if name == "init":
        return (package / "__init__.py").exists()
    modules = [p.stem for p in package.glob("*.py") if p.stem != "__init__"]
    return any(name == m or name.startswith(f"{m}_") for m in modules)


def test_every_unit_test_file_mirrors_a_src_module() -> None:
    strays = sorted(
        str(path.relative_to(REPO)).replace("\\", "/")
        for path in UNIT.rglob("test_*.py")
        if not _mirrors_a_module(path)
    )

    assert strays == [], (
        "These test files do not mirror a src module; rename them to "
        "test_<module>[_<topic>].py beside the module they test, or move "
        f"cross-module tests to tests/integration/: {strays}"
    )


def test_no_stray_test_files_outside_the_known_roots() -> None:
    roots = {"solidworks_mcp", "integration", "live"}
    strays = sorted(
        str(path.relative_to(REPO)).replace("\\", "/")
        for path in (REPO / "tests").rglob("test_*.py")
        if ".generated" not in path.parts
        and path.relative_to(REPO / "tests").parts[0] not in roots
    )

    assert strays == []
