"""Verify (and optionally fix) every "N tools" claim in the repo against the
real, AST-counted tool total.

Ground truth is computed the same way ``verify_tool_count.py`` does: every
``@mcp.tool()``/``@tool()``-decorated function under ``src/solidworks_mcp/tools/``.
That function is imported from here rather than reimplemented, so there is
exactly one counting algorithm in the repo.

Usage::

    python src/utils/check_tool_docs_consistency.py            # check only, exit 1 on drift
    python src/utils/check_tool_docs_consistency.py --fix       # rewrite the fixable locations in place
    python src/utils/check_tool_docs_consistency.py --category  # also report per-category drift (no auto-fix)

What this deliberately does NOT touch, and why:

- ``CHANGELOG.md`` — each entry is a historical, point-in-time record of what
  shipped in that release. "Rewriting history" to match today's count would
  make the changelog lie about what that version actually had.
- ``SWChecklist.md`` — its tool-count lines describe the original Node.js/
  winax implementation (explicitly marked as a historical document; see the
  banner at the top of that file). It is not a claim about current state.
- ``docs/planning/solidworks-api-coverage.md`` — its "~75 tools" figure is an
  approximate, dated audit snapshot with a whole coverage table built around
  it; swapping just the headline number without re-auditing the table would
  make it *more* misleading, not less. Flagged for manual review, not fixed.
- Anything under ``tests/`` — a test asserting a specific tool count is
  pinning a regression, not documenting current state. If it goes stale that
  is a real test failure to see and decide about, not something to silently
  patch out from under the test suite.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_tool_count import find_tools_in_file  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "src" / "solidworks_mcp" / "tools"

# Maps a tools/*.py filename to the display category name used in docs.
# Keep in sync with docs/user-guide/tools-overview.md's category cards and
# docs/user-guide/tool-catalog/*.md.
CATEGORY_LABELS: dict[str, str] = {
    "modeling.py": "Modeling",
    "sketching.py": "Sketching",
    "drawing.py": "Drawing",
    "analysis.py": "Analysis",
    "export.py": "Export",
    "file_management.py": "File Management",
    "automation.py": "Automation",
    "vba_generation.py": "VBA Generation",
    "template_management.py": "Template Management",
    "macro_recording.py": "Macro Recording",
    "docs_discovery.py": "Docs Discovery",
    "drawing_analysis.py": "Drawing Analysis",
}


@dataclass
class FixableLocation:
    path: Path
    pattern: str  # regex with one capture group around the digits to replace
    label: str


# Every place in the repo that asserts a *current* total tool count as plain
# "N tools"/"N Tools" text, safe to regex-replace in place. Order doesn't
# matter. See the module docstring for what's deliberately excluded.
FIXABLE_LOCATIONS: list[FixableLocation] = [
    FixableLocation(
        REPO_ROOT / "mkdocs.yml",
        r"(site_description:.*with )(\d+)( tools)",
        "mkdocs.yml site_description",
    ),
    FixableLocation(
        REPO_ROOT / "README.md",
        r"(SolidWorks automation with )(\d+)( tools)",
        "README.md intro line",
    ),
    FixableLocation(
        REPO_ROOT / "docs" / "index.md",
        r"(\*\*)(\d+)( Tools\*\*)",
        "docs/index.md badge line",
    ),
    FixableLocation(
        REPO_ROOT / "docs" / "index.md",
        r"(- )(\d+)( tools across)",
        "docs/index.md bullet line",
    ),
    FixableLocation(
        REPO_ROOT / "docs" / "user-guide" / "tool-catalog" / "index.md",
        r"(# Tool Catalog — All )(\d+)( Tools)",
        "tool-catalog/index.md heading",
    ),
    FixableLocation(
        REPO_ROOT / "docs" / "user-guide" / "tool-catalog" / "index.md",
        r"(documents all \*\*)(\d+)( MCP tools\*\*)",
        "tool-catalog/index.md intro line",
    ),
    FixableLocation(
        REPO_ROOT / "src" / "solidworks_mcp" / "server.py",
        r"(This server provides )(\d+)\+?( tools)",
        "server.py module docstring",
    ),
    FixableLocation(
        REPO_ROOT / "src" / "solidworks_mcp" / "__init__.py",
        r"(^)(\d+)\+?( tools)",
        "solidworks_mcp/__init__.py docstring",
    ),
    FixableLocation(
        REPO_ROOT / "docs" / "user-guide" / "tools-overview.md",
        r"(provides )(\d+)( specialized tools)",
        "tools-overview.md intro line",
    ),
    FixableLocation(
        REPO_ROOT / "docs" / "user-guide" / "tools-overview.md",
        r"(\*\*Total: )(\d+)( Tools\*\*)",
        "tools-overview.md statistics table total",
    ),
]


def get_true_counts() -> tuple[int, dict[str, int]]:
    """Ground truth: total tool count and per-file breakdown, via AST.

    Returns:
        tuple[int, dict[str, int]]: (total, {filename: count}).
    """
    per_file: dict[str, int] = {}
    for py_file in sorted(TOOLS_DIR.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        count = len(find_tools_in_file(py_file))
        if count:
            per_file[py_file.name] = count
    return sum(per_file.values()), per_file


def check_fixable(true_total: int, fix: bool) -> list[str]:
    """Check (and optionally fix) every FixableLocation. Returns problem lines."""
    problems: list[str] = []
    for loc in FIXABLE_LOCATIONS:
        if not loc.path.exists():
            problems.append(f"MISSING FILE: {loc.path} ({loc.label})")
            continue
        text = loc.path.read_text(encoding="utf-8")
        match = re.search(loc.pattern, text, flags=re.MULTILINE)
        if not match:
            problems.append(f"PATTERN NOT FOUND: {loc.label} in {loc.path.relative_to(REPO_ROOT)}")
            continue
        found = int(match.group(2))
        if found == true_total:
            continue
        problems.append(
            f"DRIFT: {loc.label} says {found} tools, actual is {true_total} "
            f"({loc.path.relative_to(REPO_ROOT)})"
        )
        if fix:
            new_text = (
                text[: match.start()]
                + match.group(1)
                + str(true_total)
                + match.group(3)
                + text[match.end() :]
            )
            loc.path.write_text(new_text, encoding="utf-8")
    return problems


def check_categories(per_file: dict[str, int]) -> list[str]:
    """Report per-category drift against docs/user-guide/tools-overview.md.

    Not auto-fixed: the overview page hand-arranges cards in prose, not a
    mechanical list, so a safe rewrite would need real judgment about layout,
    not just digit-swapping.
    """
    overview = REPO_ROOT / "docs" / "user-guide" / "tools-overview.md"
    text = overview.read_text(encoding="utf-8")
    problems: list[str] = []
    seen_labels: set[str] = set()

    for filename, true_count in per_file.items():
        label = CATEGORY_LABELS.get(filename)
        if label is None:
            problems.append(f"UNMAPPED FILE: {filename} has no entry in CATEGORY_LABELS")
            continue
        seen_labels.add(label)
        # Match this category's card by its bold heading, then the first
        # "N tools available" that follows it (before the next card starts).
        # Doesn't care what the card's link target is (same-page anchor or
        # a separate page) — only the declared count.
        heading_pattern = rf"\*\*{re.escape(label)}( Tools)?\*\*"
        heading_match = re.search(heading_pattern, text)
        if heading_match is None:
            problems.append(f"MISSING CARD: '{label}' ({true_count} tools) has no card in tools-overview.md at all")
            continue
        count_match = re.search(r"\*\*(\d+) tools? available\*\*", text[heading_match.end() :])
        match = count_match
        if match is None:
            problems.append(
                f"MISSING CARD: '{label}' ({true_count} tools) has no card in "
                f"tools-overview.md at all"
            )
            continue
        found = int(match.group(1))
        if found != true_count:
            problems.append(
                f"CATEGORY DRIFT: '{label}' card says {found} tools, actual is {true_count}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="Rewrite fixable locations in place")
    parser.add_argument(
        "--category", action="store_true", help="Also check per-category counts (report only)"
    )
    args = parser.parse_args()

    true_total, per_file = get_true_counts()
    print(f"Ground truth (AST-counted): {true_total} tools across {len(per_file)} files\n")

    problems = check_fixable(true_total, fix=args.fix)

    if args.category:
        problems += check_categories(per_file)

    if not problems:
        print("All checked locations are consistent with the current tool count.")
        return 0

    verb = "Fixed" if args.fix else "Found"
    print(f"{verb} {len([p for p in problems if p.startswith('DRIFT')])} drift issue(s):\n")
    for p in problems:
        print(f"  - {p}")

    if args.fix:
        # Re-check after fixing so the exit code reflects what's still wrong
        # (e.g. category drift, which --fix never touches).
        remaining = check_fixable(true_total, fix=False)
        if args.category:
            remaining += check_categories(per_file)
        return 1 if remaining else 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
