"""Fail when a committed tool-catalog page drifts from the generator's output."""
from __future__ import annotations

import filecmp
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "src" / "utils" / "generate_tool_catalog.py"
CATALOG_DIR = REPO_ROOT / "docs" / "user-guide" / "tool-catalog"


def test_tool_catalog_matches_generator(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--output-dir",
            str(tmp_path),
            "python",
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    committed = sorted(p.name for p in CATALOG_DIR.glob("*.md"))
    generated = sorted(p.name for p in tmp_path.glob("*.md"))
    assert committed == generated, (
        f"catalog page set differs: committed={committed} generated={generated}"
    )

    drifted = [
        name
        for name in committed
        if not filecmp.cmp(CATALOG_DIR / name, tmp_path / name, shallow=False)
    ]
    assert not drifted, f"tool catalog pages drifted from the generator: {drifted}"