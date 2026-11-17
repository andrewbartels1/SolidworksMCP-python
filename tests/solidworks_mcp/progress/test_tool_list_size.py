"""The tool list's size per toolset and mode (queue item 14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.progress import tool_list_size as size


def test_the_table_compares_each_choice_with_the_full_list() -> None:
    listings = [
        size.Listing(("all",), "list", 100, 400_000),
        size.Listing(("core",), "search", 4, 4_000),
    ]

    table = size.table(listings)

    assert table.splitlines()[2] == "| `all` | `list` | 100 | 391 KB | 100,000 | 100% |"
    assert table.splitlines()[3] == "| `core` | `search` | 4 | 4 KB | 1,000 | 1% |"


@pytest.mark.asyncio
async def test_search_mode_lists_four_tools() -> None:
    listing = await size.measure(("core",), "search")

    assert listing.tools == 4
    assert 0 < listing.tokens < 2_000


def test_main_writes_the_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(size, "build", lambda: "| table |\n")

    written = size.main(tmp_path)

    assert written == tmp_path / size.OUTPUT
    assert written.read_text(encoding="utf-8") == "| table |\n"
