"""The selftest's report: a line per area, a Markdown summary, and an issue link."""

from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import quote

from .results import AreaResult, Check, Outcome

#: The compatibility issue form; ``summary`` is the field the link fills.
ISSUE_FORM_URL = (
    "https://github.com/andrewbartels1/SolidworksMCP-python/issues/new"
    "?template=compatibility.yml"
)
#: Longest link printed; GitHub refuses much longer ones.
MAX_LINK_LENGTH = 8000


def _value(value: Any) -> str:
    """A check value as the report shows it."""
    if value is None:
        return "not measured"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:,.2f}" if abs(value) >= 1 else f"{value:g}"
    if isinstance(value, list):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    return str(value)


def _unit(unit: str) -> str:
    """A unit in plain ASCII, so a Windows console prints it."""
    return unit.replace("³", "3")


def _tolerance(check: Check) -> str:
    """A check's tolerance: relative for a volume, absolute otherwise."""
    if check.tolerance is None:
        return "exact"
    if "³" in check.unit:
        return f"{check.tolerance * 100:g} %"
    return f"{_value(check.tolerance)} {_unit(check.unit)}"


def area_line(result: AreaResult) -> str:
    """One line for an area: outcome, name, checks passed, and why if not PASS.

    Args:
        result: The area's result.

    Returns:
        str: e.g. ``PASS  part       8/8 checks``.
    """
    line = f"{result.outcome.value}  {result.name:<9}"
    if result.outcome is not Outcome.SKIP:
        line += f"  {result.passed_count}/{len(result.checks)} checks"
    if result.note:
        line += f"  {result.note}"
    return line


def _tools(calls: list[str]) -> str:
    """The tools an area called, in first-call order, with repeat counts."""
    counts = Counter(calls)
    return ", ".join(
        f"`{name}`" + (f" x{counts[name]}" if counts[name] > 1 else "")
        for name in dict.fromkeys(calls)
    )


def _templates(templates: dict[str, Any]) -> str:
    """The default templates by file name, marking any that are missing."""
    shown = []
    for kind in ("part", "assembly", "drawing"):
        entry = templates.get(kind) or {}
        name = entry.get("file_name") or "not set"
        missing = "" if entry.get("exists") else " (missing)"
        shown.append(f"{kind}: {name}{missing}")
    return "; ".join(shown)


def summary_markdown(environment: dict[str, Any], results: list[AreaResult]) -> str:
    """The summary to paste into a compatibility issue.

    Args:
        environment: From ``read_environment``.
        results: The areas' results.

    Returns:
        str: Markdown: the environment, then each area's checks and tools.
    """
    sw = environment.get("solidworks") or {}
    passed = sum(1 for r in results if r.outcome is Outcome.PASS)
    lines = [
        f"### Selftest: {passed} of {len(results)} areas passed",
        "",
        "| | |",
        "| --- | --- |",
        f"| SolidWorks | {_value(sw.get('revision'))} "
        f"(year {_value(sw.get('year'))}), {_value(sw.get('language'))} |",
        f"| Templates | {_templates(sw.get('templates') or {})} |",
        f"| OS | {_value(environment.get('os'))} |",
        f"| Python | {_value(environment.get('python'))}, "
        f"pywin32 {_value(environment.get('pywin32'))} |",
        f"| solidworks-mcp-python | {_value(environment.get('solidworks_mcp'))} |",
    ]
    for result in results:
        lines += ["", f"#### {result.name}: {result.outcome.value}"]
        if result.note:
            lines += ["", result.note]
        if result.checks:
            lines += [
                "",
                "| Check | Expected | Measured | Tolerance | Result |",
                "| --- | --- | --- | --- | --- |",
            ]
            lines += [
                f"| {c.name} | {_value(c.expected)} {_unit(c.unit)} | "
                f"{_value(c.measured)} | {_tolerance(c)} | "
                f"{'pass' if c.passed else 'FAIL'} |"
                for c in result.checks
            ]
        if result.calls:
            lines += ["", f"Tools: {_tools(result.calls)}"]
    return "\n".join(lines) + "\n"


def issue_link(summary: str) -> str | None:
    """The issue-form link with ``summary`` filled in, if it's short enough.

    Args:
        summary: The Markdown summary.

    Returns:
        str | None: The link, or ``None`` when it would be too long.
    """
    link = f"{ISSUE_FORM_URL}&summary={quote(summary)}"
    return link if len(link) <= MAX_LINK_LENGTH else None


def render(
    environment: dict[str, Any], results: list[AreaResult], problems: list[str]
) -> str:
    """Everything the command prints after the run.

    Args:
        environment: From ``read_environment``.
        results: The areas' results.
        problems: Cleanup problems, printed but kept out of the summary.

    Returns:
        str: The area lines, any cleanup problems, the summary and the link.
    """
    summary = summary_markdown(environment, results)
    parts = ["\n".join(area_line(r) for r in results)]
    if problems:
        parts.append("Cleanup:\n" + "\n".join(f"  {p}" for p in problems))
    parts.append("Summary to paste into a compatibility report:\n\n" + summary)
    link = issue_link(summary)
    if link:
        parts.append(f"Open the report form with this summary filled in:\n{link}")
    else:
        parts.append(
            "Open the report form and paste the summary above:\n" + ISSUE_FORM_URL
        )
    return "\n\n".join(parts) + "\n"
