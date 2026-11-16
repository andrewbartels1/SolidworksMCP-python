"""``python -m solidworks_mcp.doc_links build|check|check-external``.

- ``build`` writes ``docs/llms.txt``.
- ``check`` (offline) checks ``docs/llms.txt`` against the docs and every
  link to this project's own pages and files.
- ``check-external`` (online) visits every link to another site and writes
  ``tests/.generated/link-report.md``.

Each exits 1 when something fails.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

from .links import all_links, check_external, check_internal, is_external, report
from .llms_txt import LLMS_TXT, build, check
from .pages import DocsError, load_site

#: Where ``check-external`` writes its report.
REPORT = Path("tests/.generated/link-report.md")


def main(argv: list[str] | None = None) -> int:
    """Run one command.

    Args:
        argv: The arguments (``sys.argv[1:]`` when omitted).

    Returns:
        The exit code: 0 when it passed, 1 when it found a problem.
    """
    parser = argparse.ArgumentParser(prog="python -m solidworks_mcp.doc_links")
    parser.add_argument("command", choices=("build", "check", "check-external"))
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    args = parser.parse_args(argv)
    root: Path = args.root
    if args.command == "build":
        return _build(root)
    if args.command == "check":
        return _check(root)
    return _check_external(root)


def _build(root: Path) -> int:
    """Write ``docs/llms.txt``."""
    try:
        text = build(root)
    except DocsError as error:
        logger.error(str(error))
        return 1
    (root / LLMS_TXT).write_text(text, encoding="utf-8", newline="\n")
    logger.info(f"wrote {LLMS_TXT} ({text.count(chr(10) + '- [')} pages)")
    return 0


def _check(root: Path) -> int:
    """The offline checks: ``llms.txt``, then every link within the project."""
    problems = check(root)
    links = all_links(root)
    problems += check_internal(root, load_site(root), links)
    for problem in problems:
        logger.error(problem)
    internal = sum(1 for link in links if not is_external(link.target))
    logger.info(
        f"{len(links)} links found, {internal} relative; {len(problems)} problems"
    )
    return 1 if problems else 0


def _check_external(root: Path) -> int:
    """The online check, with its report written under ``tests/.generated/``."""
    results = asyncio.run(check_external(all_links(root)))
    out = root / REPORT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report(results), encoding="utf-8", newline="\n")
    failed = [r for r in results if not r.ok]
    for result in failed:
        went = f" -> {result.final_url}" if result.final_url else ""
        logger.error(f"{result.url}: {result.detail}{went} ({', '.join(result.where)})")
    logger.info(f"{len(results)} URLs visited, {len(failed)} failed; report: {REPORT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
