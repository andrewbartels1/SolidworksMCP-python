"""Reading the docs: nav, page openings and heading ids (spec: docs/llms-txt)."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.doc_links.pages import (
    OVERVIEW,
    DocsError,
    NavPage,
    heading_ids,
    heading_text,
    load_site,
    nav_pages,
    opening,
    page_url,
    slugify,
    source_lines,
)

from .conftest import REPO, SITE

_ROOT = Path(__file__).resolve().parents[3]


def test_load_site_reads_settings_and_ignores_python_tags(site_root: Path) -> None:
    site = load_site(site_root)

    assert (site.name, site.description) == ("Proj", "A test project")
    assert (site.url, site.repo_url) == (SITE, REPO)
    assert site.nav[0] == {"Home": "index.md"}


def test_nav_pages_in_order_without_api_or_missing(site_root: Path) -> None:
    pages = nav_pages(load_site(site_root).nav, site_root / "docs")

    assert pages == [
        NavPage(OVERVIEW, "index.md"),
        NavPage("Guide", "guide/start.md"),
        NavPage("Guide", "guide/more.md"),
    ]


def test_nav_pages_accepts_untitled_entries(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")

    assert nav_pages(["a.md", {"S": ["a.md"]}], tmp_path) == [
        NavPage(OVERVIEW, "a.md"),
        NavPage("S", "a.md"),
    ]


@pytest.mark.parametrize(
    ("path", "url"),
    [
        ("index.md", f"{SITE}/"),
        ("guide/start.md", f"{SITE}/guide/start/"),
        ("guide/index.md", f"{SITE}/guide/"),
    ],
)
def test_page_url(path: str, url: str) -> None:
    assert page_url(SITE, path) == url


def test_source_lines_marks_code_and_blanks_front_matter() -> None:
    text = "---\na: 1\n---\n# T\n```py\nx\n```\nafter\n~~~\n```\n~~~\n"

    lines = source_lines(text)

    assert lines[0] == (1, "", False)
    assert [code for _n, _l, code in lines[4:8]] == [True, True, True, False]
    assert all(code for _n, _l, code in lines[8:11])


def test_opening_takes_title_and_first_prose_paragraph() -> None:
    text = (
        "# Start here {#top}\n\n> A note.\n\n!!! tip\n    hi\n\n- a list\n\n"
        "| t |\n\n![img](x.png)\n\n[![badge](b.svg)](u)\n\n<div>x</div>\n\n"
        '=== "Tab"\n\n    indented code\n\n```\ncode\n```\n'
        "Use `[not](a link)` and [uv](https://x.y), ![alt](i.png),\n"
        "[ref][r] or <https://a.b>.\n\n## Next\n"
    )

    start = opening(text, "p.md")

    assert start.title == "Start here"
    assert start.summary == ("Use `[not](a link)` and uv, alt, ref or https://a.b.")


def test_opening_paragraph_at_end_of_file() -> None:
    assert opening("# T\n\nLast words", "p.md").summary == "Last words"


def test_opening_without_title_raises() -> None:
    with pytest.raises(DocsError, match="p.md: no `# ` heading"):
        opening("Just text\n", "p.md")


def test_opening_without_paragraph_raises() -> None:
    with pytest.raises(DocsError, match="p.md: no opening paragraph"):
        opening("# T\n\n- only a list\n\n## Next\n\nlater\n", "p.md")


def test_heading_text_drops_markup() -> None:
    assert heading_text("The **`save_file`** [tool](x) <b>now</b>") == (
        "The save_file tool now"
    )


@pytest.mark.parametrize(
    ("value", "slug"),
    [
        ("Tool names", "tool-names"),
        ("1. Implemented Tools", "1-implemented-tools"),
        ("Missing Medium/Low  Priority", "missing-mediumlow-priority"),
        ("Café — déjà vu", "cafe-deja-vu"),
    ],
)
def test_slugify(value: str, slug: str) -> None:
    assert slugify(value) == slug


def test_heading_ids_repeats_explicit_and_attribute_ids() -> None:
    text = (
        "# Title\n\n## Details\n\n## Details\n\n## Other {#mine .cls}\n\n"
        '## Plain {.cls}\n\nPara\n{: #para-id }\n\n<a id="html-id"></a>\n\n'
        "```\n## Not a heading\n```\n"
    )

    assert heading_ids(text) == {
        "title",
        "details",
        "details_1",
        "mine",
        "plain",
        "para-id",
        "html-id",
    }


def test_slugify_matches_python_markdown_on_every_docs_heading() -> None:
    toc = pytest.importorskip("markdown.extensions.toc")
    import re

    checked = 0
    for page in sorted((_ROOT / "docs").rglob("*.md")):
        for _n, line, code in source_lines(page.read_text(encoding="utf-8")):
            heading = None if code else re.match(r"^#{1,6}\s+(.*?)\s*$", line)
            if heading and "{" not in heading.group(1):
                text = heading_text(heading.group(1))
                assert slugify(text) == toc.slugify(text, "-"), (page, text)
                checked += 1
    assert checked > 100
