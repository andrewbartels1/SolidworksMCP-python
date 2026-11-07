"""The committed progress image and data match the code (spec: docs/coverage-progress).

Adding a tool, changing a level or calling new COM methods in an adapter
changes them; regenerate with ``python -m solidworks_mcp.progress.generate``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.progress.generate import OUTPUT_DIR, build

_ROOT = Path(__file__).resolve().parents[2]
_COMMAND = "python -m solidworks_mcp.progress.generate"


@pytest.fixture(scope="module")
def generated() -> dict[str, str]:
    return build(_ROOT)


@pytest.mark.parametrize("name", ["progress.svg", "progress.json", "tables.html"])
def test_the_committed_file_is_up_to_date(name: str, generated: dict[str, str]) -> None:
    committed = (_ROOT / OUTPUT_DIR / name).read_text(encoding="utf-8")

    assert committed == generated[name], (
        f"{OUTPUT_DIR / name} is out of date; run `{_COMMAND}` and commit it."
    )
