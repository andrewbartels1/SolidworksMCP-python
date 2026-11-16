"""Build ``docs/llms.txt`` from the docs, and check a committed copy.

The file follows the llms.txt format: a ``# `` title, a ``> `` summary,
then ``## `` sections of ``- [title](url): summary`` entries. Every title
and summary is copied word for word from the page it links to (see
:func:`.pages.opening`), and the same content rules hold for the builder
and the checker, so a hand edit can't match a bad build.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .pages import DocsError, Site, load_site, nav_pages, opening, page_url

#: Where the file lives (MkDocs copies it to the site root).
LLMS_TXT = Path("docs/llms.txt")
#: The command that rebuilds it.
BUILD_COMMAND = "python -m solidworks_mcp.doc_links build"

_ENTRY = re.compile(r"^- \[(?P<title>[^\]]+)\]\((?P<url>\S+)\): (?P<summary>\S.*)$")
_SHAPES = (
    re.compile(r"^# \S.*$"),
    re.compile(r"^> \S.*$"),
    re.compile(r"^## \S.*$"),
    _ENTRY,
    re.compile(r"^$"),
)
_URL = re.compile(r"[a-z][a-z0-9+.-]*://[^\s)>\]]+", re.IGNORECASE)
_CODE_SPAN = re.compile(r"(`+).+?\1")
_HTML = re.compile(r"<(?:[A-Za-z/]|!--)")


@dataclass(frozen=True)
class Entry:
    """One page's line in ``llms.txt``.

    Attributes:
        section: Its ``## `` section.
        page: The page's path under ``docs/``.
        title: The page's title.
        url: The page's published URL.
        summary: The page's opening paragraph.
    """

    section: str
    page: str
    title: str
    url: str
    summary: str

    @property
    def line(self) -> str:
        """The entry as it appears in the file."""
        return f"- [{self.title}]({self.url}): {self.summary}"


def entries(root: Path, site: Site | None = None) -> list[Entry]:
    """Every nav page's entry, in nav order.

    Args:
        root: The repository root.
        site: The site settings, read from ``mkdocs.yml`` when omitted.

    Returns:
        The entries.

    Raises:
        DocsError: When a page has no title or opening paragraph, or its
            title or opening breaks a content rule.
    """
    site = site or load_site(root)
    docs = root / "docs"
    found: list[Entry] = []
    for page in nav_pages(site.nav, docs):
        start = opening((docs / page.path).read_text(encoding="utf-8"), page.path)
        entry = Entry(
            page.section,
            page.path,
            start.title,
            page_url(site.url, page.path),
            start.summary,
        )
        problems = line_problems(entry.line, site)
        if problems:
            raise DocsError(f"{page.path}: {problems[0]}")
        found.append(entry)
    return found


def build(root: Path) -> str:
    """The text of ``llms.txt`` for the docs under ``root``.

    Args:
        root: The repository root.

    Returns:
        The file's text, ending in a newline.

    Raises:
        DocsError: As :func:`entries`, or when the site name or
            description breaks a content rule.
    """
    site = load_site(root)
    lines = [f"# {site.name}", "", f"> {site.description}"]
    section = None
    for entry in entries(root, site):
        if entry.section != section:
            section = entry.section
            lines += ["", f"## {section}", ""]
        lines.append(entry.line)
    for line in lines[:3]:
        problems = line_problems(line, site)
        if problems:
            raise DocsError(f"mkdocs.yml: {problems[0]}")
    return "\n".join(lines) + "\n"


def line_problems(line: str, site: Site) -> list[str]:
    """What is wrong with one line of ``llms.txt``, if anything.

    The rules (spec ``docs/llms-txt``): one of the allowed shapes; every URL
    under ``site_url`` or ``repo_url``; no control or format characters
    (zero-width, byte-order mark, bidirectional controls); no HTML tag or
    comment outside code spans.

    Args:
        line: The line, without its line break.
        site: The site settings (for the allowed URLs).

    Returns:
        A message per problem; empty when the line is fine.
    """
    problems: list[str] = []
    for char in line:
        if unicodedata.category(char) in ("Cc", "Cf"):
            problems.append(
                f"hidden character U+{ord(char):04X} "
                f"({unicodedata.name(char, 'unnamed')})"
            )
    if _HTML.search(_CODE_SPAN.sub("", line)):
        problems.append("HTML tag or comment")
    for url in _URL.findall(line):
        if not _ours(url, site):
            problems.append(f"link outside this project: {url}")
    if not any(shape.match(line) for shape in _SHAPES):
        problems.append("not a title, summary, section, entry or blank line")
    return problems


def _ours(url: str, site: Site) -> bool:
    """Whether ``url`` is the docs site or this repository."""
    return any(
        url == base or url.startswith(base + "/") for base in (site.url, site.repo_url)
    )


def check(root: Path, committed: str | None = None) -> list[str]:
    """Problems with the committed ``llms.txt``; empty when it is right.

    Args:
        root: The repository root.
        committed: The file's text; read from ``docs/llms.txt`` when omitted.

    Returns:
        One message per problem: a content rule broken (with its line
        number), an entry whose title or summary differs from its page
        (with the expected and the found text), a page missing or extra,
        or else the first line that differs. Each ends by naming the
        rebuild command when the fix is a rebuild.
    """
    site = load_site(root)
    if committed is None:
        path = root / LLMS_TXT
        if not path.is_file():
            return [f"{LLMS_TXT} is missing; run `{BUILD_COMMAND}`"]
        committed = path.read_text(encoding="utf-8")
    problems = [
        f"{LLMS_TXT}:{number}: {problem}"
        for number, line in enumerate(committed.split("\n"), start=1)
        for problem in line_problems(line, site)
    ]
    try:
        expected = build(root)
    except DocsError as error:
        return [*problems, str(error)]
    if committed == expected:
        return problems
    problems += _entry_differences(committed, entries(root, site))
    if not problems:
        problems.append(_first_difference(committed, expected))
    return problems


def _entry_differences(committed: str, expected: list[Entry]) -> list[str]:
    """Entries whose title or summary differs from the page, or are missing/extra."""
    found: dict[str, tuple[int, str, str]] = {}
    for number, line in enumerate(committed.split("\n"), start=1):
        match = _ENTRY.match(line)
        if match:
            found[match["url"]] = (number, match["title"], match["summary"])
    problems: list[str] = []
    for entry in expected:
        if entry.url not in found:
            problems.append(
                f"{LLMS_TXT}: no entry for {entry.page}; run `{BUILD_COMMAND}`"
            )
            continue
        number, title, summary = found.pop(entry.url)
        for field, want, got in (
            ("title", entry.title, title),
            ("summary", entry.summary, summary),
        ):
            if want != got:
                problems.append(
                    f"{LLMS_TXT}:{number}: the {field} doesn't match {entry.page}\n"
                    f"  expected: {want}\n  found:    {got}"
                )
    for url, (number, _title, _summary) in found.items():
        problems.append(
            f"{LLMS_TXT}:{number}: {url} is not a page in the nav; "
            f"run `{BUILD_COMMAND}`"
        )
    return problems


def _first_difference(committed: str, expected: str) -> str:
    """The first line where the committed file and a fresh build differ."""
    have, want = committed.split("\n"), expected.split("\n")
    for number, (got, line) in enumerate(zip(have, want, strict=False), start=1):
        if got != line:
            return (
                f"{LLMS_TXT}:{number}: out of date (expected {line!r}, found "
                f"{got!r}); run `{BUILD_COMMAND}`"
            )
    return (
        f"{LLMS_TXT}:{min(len(have), len(want)) + 1}: out of date (the file is "
        f"{'longer' if len(have) > len(want) else 'shorter'} than a fresh build); "
        f"run `{BUILD_COMMAND}`"
    )
