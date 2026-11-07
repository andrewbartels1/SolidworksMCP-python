"""Regenerate the progress image, its data and the docs page's tables.

Run from the repository root after adding a tool, changing a level or
calling new COM methods in an adapter::

    python -m solidworks_mcp.progress.generate

It writes, under ``docs/assets/progress/``:

- ``progress.svg``: the README image;
- ``progress.json``: every tool's family, level and summary, and the
  coverage of each core interface;
- ``tables.html``: the docs page's HTML tables, readable without scripts.

``tests/integration/test_progress_up_to_date.py`` fails when any of them is
out of date.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.utilities.docstring_parsing import parse_docstring

from ..adapters.mock_adapter import MockSolidWorksAdapter
from ..tools import register_tools
from ..tools.support_levels import SUPPORT_LEVELS, SupportLevel
from ..tools.tool_boundary import tool_family
from .com_coverage import ComCoverage, Snapshot, adapter_sources, called_names, measure
from .snapshot import SNAPSHOT_PATH
from .svg import render

#: The generated files, relative to the repository root.
OUTPUT_DIR = Path("docs/assets/progress")
OUTPUTS = ("progress.svg", "progress.json", "tables.html")

# Material for MkDocs wraps Markdown tables in these so wide ones scroll;
# raw HTML tables need them written out.
_WRAP_OPEN = '<div class="md-typeset__scrollwrap"><div class="md-typeset__table">'
_WRAP_CLOSE = "</div></div>"


@dataclass(frozen=True)
class ToolRow:
    """One registered tool, as the progress page lists it.

    Attributes:
        name: The tool name.
        family: Its family (the module that defines it).
        level: Its support level.
        reason: Why it isn't stable (empty when it is).
        summary: The first paragraph of its docstring.
    """

    name: str
    family: str
    level: SupportLevel
    reason: str
    summary: str


async def tool_rows() -> list[ToolRow]:
    """Every registered tool, sorted by name.

    Returns:
        list[ToolRow]: One row per tool.
    """
    mcp = FastMCP("progress")
    await register_tools(mcp, MockSolidWorksAdapter({}), {})
    rows = []
    for tool in await mcp.list_tools():
        support = SUPPORT_LEVELS[tool.name]
        text = parse_docstring(tool.fn).description or ""
        rows.append(
            ToolRow(
                tool.name,
                tool_family(tool.fn),
                support.level,
                support.reason,
                " ".join(text.split("\n\n", 1)[0].split()),
            )
        )
    return sorted(rows, key=lambda r: r.name)


def progress_json(rows: list[ToolRow], coverage: ComCoverage) -> str:
    """The data behind the image and the page.

    Args:
        rows: Every tool.
        coverage: The COM coverage.

    Returns:
        str: JSON text ending in a newline.
    """
    counts = Counter(r.level for r in rows)
    data: dict[str, Any] = {
        "tools": {
            "total": len(rows),
            "by_level": {level.value: counts[level] for level in SupportLevel},
            "list": [
                {
                    "name": r.name,
                    "family": r.family,
                    "level": r.level.value,
                    "reason": r.reason,
                    "summary": r.summary,
                }
                for r in rows
            ],
        },
        "com": {
            "type_library": coverage.type_library,
            "core": {"covered": coverage.core_covered, "total": coverage.core_total},
            "api": {"covered": coverage.api_covered, "total": coverage.api_total},
            "interfaces": [
                {"name": i.name, "covered": list(i.covered), "total": i.total}
                for i in coverage.interfaces
            ],
        },
    }
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def tables_html(rows: list[ToolRow], coverage: ComCoverage) -> str:
    """The page's two tables, as HTML the docs page includes.

    Each tool row carries ``data-level`` and ``data-family`` for the filter
    script, and its level as text as well as colour.

    Args:
        rows: Every tool.
        coverage: The COM coverage.

    Returns:
        str: The HTML.
    """
    out = [
        _WRAP_OPEN,
        '<table data-progress="tools">',
        "<thead><tr><th>Tool</th><th>Family</th><th>Level</th>"
        "<th>What it does</th></tr></thead>",
        "<tbody>",
    ]
    for r in rows:
        note = f"<br><small>{escape(r.reason)}</small>" if r.reason else ""
        out.append(
            f'<tr data-level="{r.level.value}" data-family="{r.family}">'
            f'<td title="{escape(r.summary)}"><code>{r.name}</code></td>'
            f"<td>{r.family}</td>"
            f'<td><span class="level level-{r.level.value}">{r.level.value}</span>'
            f"{note}</td><td>{escape(r.summary)}</td></tr>"
        )
    out += ["</tbody>", "</table>", _WRAP_CLOSE, ""]
    out += [
        _WRAP_OPEN,
        '<table data-progress="com">',
        "<thead><tr><th>Interface</th><th>Methods called</th><th>Of</th>"
        "<th>Called</th></tr></thead>",
        "<tbody>",
    ]
    for i in coverage.interfaces:
        pct = 100.0 * len(i.covered) / i.total if i.total else 0.0
        names = ", ".join(i.covered)
        out.append(
            f"<tr><td><code>{i.name}</code></td><td>{len(i.covered)}</td>"
            f"<td>{i.total}</td><td><details><summary>{pct:.1f}%</summary>"
            f"<small>{escape(names) or 'none yet'}</small></details></td></tr>"
        )
    out += ["</tbody>", "</table>", _WRAP_CLOSE, ""]
    return "\n".join(out)


def build(root: Path) -> dict[str, str]:
    """Every generated file's content, from the code under ``root``.

    Args:
        root: The repository root.

    Returns:
        dict[str, str]: File name (in ``OUTPUT_DIR``) to content.
    """
    rows = asyncio.run(tool_rows())
    coverage = measure(
        Snapshot.load(root / SNAPSHOT_PATH),
        called_names(adapter_sources(root / "src/solidworks_mcp/adapters")),
    )
    counts = Counter(r.level for r in rows)
    return {
        "progress.svg": render(counts, coverage),
        "progress.json": progress_json(rows, coverage),
        "tables.html": tables_html(rows, coverage),
    }


def main(root: Path | None = None) -> list[Path]:
    """Write the generated files under ``root``.

    Args:
        root: The repository root; the current directory when omitted.

    Returns:
        list[Path]: The files written.
    """
    base = root or Path.cwd()
    written = []
    for name, content in build(base).items():
        path = base / OUTPUT_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


if __name__ == "__main__":
    for written_path in main():
        print(written_path)
