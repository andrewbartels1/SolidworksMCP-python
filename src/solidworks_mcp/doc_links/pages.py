"""Read the docs: the mkdocs nav, and each page's title, opening and anchors.

Everything here reads Markdown source; nothing renders it. The rules for
what counts as a page's opening paragraph are in the ``docs/llms-txt``
spec, and heading ids follow Python-Markdown's ``toc`` extension, which
the docs site uses.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

#: The section that holds the nav's top-level pages.
OVERVIEW = "Overview"


class DocsError(Exception):
    """A page can't give what ``llms.txt`` needs from it (names the page)."""


#: ``!!python/name:...`` tags in ``mkdocs.yml`` (Markdown extension
#: callables). Only the site settings and the nav are needed here, so each tag
#: is read as ``null`` and the file goes through ``yaml.safe_load``: nothing
#: is ever imported or built from it.
_PYTHON_TAG = re.compile(r"!!python/\S+")


@dataclass(frozen=True)
class Site:
    """The settings ``llms.txt`` and the link checks use.

    Attributes:
        name: ``site_name``.
        description: ``site_description``.
        url: ``site_url``, without a trailing slash.
        repo_url: ``repo_url``, without a trailing slash.
        nav: The nav as written in ``mkdocs.yml``.
    """

    name: str
    description: str
    url: str
    repo_url: str
    nav: list[Any]


def load_site(root: Path) -> Site:
    """Read ``mkdocs.yml`` under ``root``.

    Args:
        root: The repository root.

    Returns:
        The site settings and nav.
    """
    text = (root / "mkdocs.yml").read_text(encoding="utf-8")
    config = yaml.safe_load(_PYTHON_TAG.sub("null", text))
    return Site(
        name=config["site_name"],
        description=config["site_description"],
        url=config["site_url"].rstrip("/"),
        repo_url=config["repo_url"].rstrip("/"),
        nav=config["nav"],
    )


@dataclass(frozen=True)
class NavPage:
    """A Markdown page listed in the nav.

    Attributes:
        section: The top-level nav section it is under (``Overview`` for
            top-level pages).
        path: Its path relative to ``docs/``, with forward slashes.
    """

    section: str
    path: str


def nav_pages(nav: list[Any], docs_dir: Path) -> list[NavPage]:
    """The nav's Markdown pages, in nav order.

    Entries that are not ``.md`` files in ``docs_dir`` (the generated API
    reference, for one) are left out.

    Args:
        nav: The nav from ``mkdocs.yml``.
        docs_dir: The ``docs/`` directory.

    Returns:
        One entry per page; top-level pages first, under ``Overview``.
    """
    top: list[NavPage] = []
    sections: list[NavPage] = []
    for item in nav:
        for title, value in _entries(item):
            if isinstance(value, list):
                sections.extend(NavPage(title, path) for path in _paths(value))
            elif isinstance(value, str):
                top.append(NavPage(OVERVIEW, value))
    return [p for p in top + sections if _is_page(p.path, docs_dir)]


def _entries(item: Any) -> Iterator[tuple[str, Any]]:
    """The (title, value) pairs of one nav item (a bare path has no title)."""
    if isinstance(item, dict):
        yield from item.items()
    else:
        yield "", item


def _paths(items: list[Any]) -> Iterator[str]:
    """Every page path in a nav section, nested sections included, in order."""
    for item in items:
        for _title, value in _entries(item):
            if isinstance(value, list):
                yield from _paths(value)
            elif isinstance(value, str):
                yield value


def _is_page(path: str, docs_dir: Path) -> bool:
    """Whether ``path`` is a Markdown file in ``docs_dir``."""
    return path.endswith(".md") and (docs_dir / path).is_file()


def page_url(site_url: str, path: str) -> str:
    """The published URL of the page at ``path`` (directory URLs).

    Args:
        site_url: ``site_url`` without a trailing slash.
        path: The page's path relative to ``docs/``.

    Returns:
        ``index.md`` -> ``<site_url>/``; ``a/b.md`` -> ``<site_url>/a/b/``;
        ``a/index.md`` -> ``<site_url>/a/``.
    """
    stem = path.removesuffix(".md")
    if stem == "index":
        return f"{site_url}/"
    stem = stem.removesuffix("/index")
    return f"{site_url}/{stem}/"


# ---------------------------------------------------------------------------
# Markdown source


_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ATTRS = re.compile(r"\s*\{([^{}]*)\}\s*$")
_ATTR_ID = re.compile(r"\{:?[^{}]*#([\w-]+)[^{}]*\}")
_HTML_ID = re.compile(r"""(?<![\w-])id=["']([\w-]+)["']""")
_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def source_lines(text: str) -> list[tuple[int, str, bool]]:
    """The page's lines as (line number, text, inside a fenced code block).

    Front matter, if any, is blanked out (its lines kept so line numbers
    still match the file). Fence lines themselves count as code.

    Args:
        text: The page's Markdown.

    Returns:
        One tuple per line, numbered from 1.
    """
    front = _FRONT_MATTER.match(text)
    if front:
        blank = "\n" * front.group(0).count("\n")
        text = blank + text[front.end() :]
    lines: list[tuple[int, str, bool]] = []
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        opened = _FENCE.match(line)
        if fence is None and opened:
            fence = opened.group(1)
            lines.append((number, line, True))
        elif fence is not None:
            if line.strip().startswith(fence):
                fence = None
            lines.append((number, line, True))
        else:
            lines.append((number, line, False))
    return lines


def _split_attrs(text: str) -> tuple[str, str | None]:
    """Split a heading's trailing ``{#id .class}`` off; return (text, id)."""
    attrs = _ATTRS.search(text)
    if not attrs:
        return text, None
    ids = re.findall(r"#([\w-]+)", attrs.group(1))
    return text[: attrs.start()], (ids[0] if ids else None)


@dataclass(frozen=True)
class Opening:
    """A page's title and opening paragraph.

    Attributes:
        title: The ``# `` heading, as written (attributes removed).
        summary: The first prose paragraph, links reduced to their text,
            lines joined with single spaces.
    """

    title: str
    summary: str


_NOT_PROSE = re.compile(
    r"^\s*(>|!!!|\?\?\?|===|[-*+]\s|\d+[.)]\s|\||<|!\[|\[!\[|---|\*\*\*|___|:::)"
)


def opening(text: str, page: str) -> Opening:
    """The page's ``# `` title and its first prose paragraph.

    Prose is a paragraph before the first lower heading that is not a
    blockquote, admonition, list, table, image, badge line, HTML, rule or
    code (fenced or indented).

    Args:
        text: The page's Markdown.
        page: The page's path, for the error message.

    Returns:
        The title and summary.

    Raises:
        DocsError: When the page has no ``# `` heading, or no prose
            paragraph before its next heading.
    """
    lines = source_lines(text)
    title: str | None = None
    block: list[str] = []
    for _number, line, code in lines:
        heading = None if code else _HEADING.match(line)
        if title is None:
            if heading and len(heading.group(1)) == 1:
                title = _split_attrs(heading.group(2))[0]
            continue
        if heading:
            break
        if code or line.strip() == "":
            if _is_prose(block):
                return Opening(title, _inline_text(" ".join(block)))
            block = []
            continue
        block.append(line.strip() if block else line)
    if title is None:
        raise DocsError(f"{page}: no `# ` heading to use as its title")
    if _is_prose(block):
        return Opening(title, _inline_text(" ".join(block)))
    raise DocsError(
        f"{page}: no opening paragraph after its `# ` heading (a blockquote, "
        "list, table, image or code doesn't count); give the page one"
    )


def _is_prose(block: list[str]) -> bool:
    """Whether a paragraph's lines (first line unstripped) are prose."""
    if not block:
        return False
    first = block[0]
    if first.startswith(("    ", "\t")):
        return False
    return not _NOT_PROSE.match(first)


_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_INLINE_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_REF_LINK = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_AUTOLINK = re.compile(r"<((?:https?|mailto):[^>\s]+)>")


def _inline_text(text: str) -> str:
    """Reduce links and images to their text, leaving code spans as written.

    Code spans are set aside first, so link syntax inside one is kept, and
    a link whose text is a code span (``[`x.py`](x.py)``) becomes the span.
    """
    spans: list[str] = []

    def hold(match: re.Match[str]) -> str:
        spans.append(match.group(0))
        return f"\x00{len(spans) - 1}\x00"

    held = _strip_links(_CODE_SPAN.sub(hold, text))
    restored = re.sub("\x00(\\d+)\x00", lambda m: spans[int(m.group(1))], held)
    return re.sub(r"\s+", " ", restored).strip()


def _strip_links(text: str) -> str:
    """Links and images in plain (non-code) text, reduced to their text."""
    text = _IMAGE.sub(r"\1", text)
    text = _INLINE_LINK.sub(r"\1", text)
    text = _REF_LINK.sub(r"\1", text)
    return _AUTOLINK.sub(r"\1", text)


# ---------------------------------------------------------------------------
# Heading ids


def slugify(value: str, separator: str = "-") -> str:
    """Python-Markdown's default ``toc`` slugify, without needing ``markdown``.

    Args:
        value: The heading's text.
        separator: What spaces and hyphens become.

    Returns:
        The heading's id.
    """
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(rf"[{separator}\s]+", separator, value)


def heading_text(raw: str) -> str:
    """A heading's text as the ``toc`` extension sees it, before slugifying.

    Links become their text, code spans their content, and emphasis
    markers and HTML tags go.

    Args:
        raw: The heading as written, attributes removed.

    Returns:
        Its plain text.
    """
    text = _strip_links(raw)
    text = _CODE_SPAN.sub(r"\2", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"(\*\*|__|\*)", "", text)


def heading_ids(text: str) -> set[str]:
    """Every anchor the page's headings get, and every ``{#id}`` it sets.

    Repeated slugs get ``_1``, ``_2`` in page order, as the ``toc``
    extension makes them.

    Args:
        text: The page's Markdown.

    Returns:
        The ids.
    """
    ids: set[str] = set()
    for _number, line, code in source_lines(text):
        if code:
            continue
        heading = _HEADING.match(line)
        if heading:
            raw, explicit = _split_attrs(heading.group(2))
            ids.add(explicit or _unique(slugify(heading_text(raw)), ids))
        else:
            ids.update(_ATTR_ID.findall(line))
            ids.update(_HTML_ID.findall(line))
    return ids


def _unique(slug: str, taken: set[str]) -> str:
    """``slug``, or ``slug_1``, ``slug_2``, ... when it is already taken."""
    candidate, n = slug, 0
    while candidate in taken:
        n += 1
        candidate = f"{slug}_{n}"
    return candidate
