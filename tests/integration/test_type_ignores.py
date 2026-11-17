"""Every ``# type: ignore`` in the package names its error code (spec: release/type-checking)."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "solidworks_mcp"

#: ``# type: ignore`` not followed by ``[code]``.
_BARE = re.compile(r"#\s*type:\s*ignore(?!\[)")


def bare_ignores(root: Path) -> list[str]:
    """``file:line`` of every bare ``# type: ignore`` under ``root``."""
    found = []
    for path in sorted(root.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _BARE.search(line):
                found.append(f"{path.relative_to(root)}:{number}")
    return found


def test_no_bare_type_ignore() -> None:
    assert bare_ignores(SRC) == []


def test_a_bare_ignore_is_found(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(
        "x = 1  # type: ignore\ny = 2  # type: ignore[assignment]\n", encoding="utf-8"
    )
    assert bare_ignores(tmp_path) == ["m.py:1"]
