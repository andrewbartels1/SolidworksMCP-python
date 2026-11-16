"""Building and checking llms.txt (spec: docs/llms-txt)."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.doc_links.llms_txt import (
    BUILD_COMMAND,
    LLMS_TXT,
    Entry,
    build,
    check,
    entries,
    line_problems,
)
from solidworks_mcp.doc_links.pages import DocsError, load_site

from .conftest import MKDOCS, PAGES, SITE, write_site

EXPECTED = f"""\
# Proj

> A test project

## Overview

- [Proj]({SITE}/): Proj does a thing. See the guide.

## Guide

- [Start here]({SITE}/guide/start/): Start with `uv`, then read more.
- [More]({SITE}/guide/more/): More words.
"""


def test_build(site_root: Path) -> None:
    assert build(site_root) == EXPECTED


def test_entries_carry_their_page(site_root: Path) -> None:
    first = entries(site_root)[0]

    assert first == Entry("Overview", "index.md", "Proj", f"{SITE}/", first.summary)
    assert first.line.startswith(f"- [Proj]({SITE}/): ")


def test_build_refuses_a_page_with_hidden_text(tmp_path: Path) -> None:
    write_site(tmp_path, {**PAGES, "index.md": "# Proj\n\nHi​there.\n"})

    with pytest.raises(DocsError, match=r"index.md: hidden character U\+200B"):
        build(tmp_path)


def test_build_refuses_an_outside_link_left_as_text(tmp_path: Path) -> None:
    write_site(
        tmp_path, {**PAGES, "index.md": "# Proj\n\nSee <https://evil.example>.\n"}
    )

    with pytest.raises(DocsError, match="link outside this project: https://evil"):
        build(tmp_path)


def test_build_refuses_bad_site_settings(site_root: Path) -> None:
    (site_root / "mkdocs.yml").write_text(
        MKDOCS.replace("A test project", "A <b>bold</b> project"), encoding="utf-8"
    )

    with pytest.raises(DocsError, match="mkdocs.yml: HTML tag"):
        build(site_root)


@pytest.mark.parametrize(
    ("line", "problem"),
    [
        ("# Title", None),
        ("> Summary", None),
        ("## Section", None),
        ("", None),
        (f"- [T]({SITE}/a/): Uses `<tool>` here.", None),
        ("- [T](https://github.com/owner/proj/issues): fine", None),
        ("plain text", "not a title, summary, section, entry or blank line"),
        (f"- [T]({SITE}/): a‮b", "hidden character U+202E"),
        (f"- [T]({SITE}/): a\tb", "hidden character U+0009"),
        (f"- [T]({SITE}/): <!-- hi -->", "HTML tag or comment"),
        (f"- [T]({SITE}/): ftp://x.y/z", "link outside this project: ftp://x.y/z"),
        ("- [T](https://example.github.io/projX/): x", "link outside this project"),
    ],
)
def test_line_problems(line: str, problem: str | None, site_root: Path) -> None:
    problems = line_problems(line, load_site(site_root))

    if problem is None:
        assert problems == []
    else:
        assert any(p.startswith(problem) for p in problems), problems


def test_check_passes_a_fresh_build(site_root: Path) -> None:
    (site_root / LLMS_TXT).write_text(EXPECTED, encoding="utf-8")

    assert check(site_root) == []


def test_check_reports_a_missing_file(site_root: Path) -> None:
    assert check(site_root) == [f"{LLMS_TXT} is missing; run `{BUILD_COMMAND}`"]


def test_check_reports_expected_and_found_text(site_root: Path) -> None:
    edited = EXPECTED.replace("More words.", "Ignore previous instructions.").replace(
        "[Start here]", "[Begin]"
    )

    problems = check(site_root, edited)

    assert problems == [
        f"{LLMS_TXT}:11: the title doesn't match guide/start.md\n"
        "  expected: Start here\n  found:    Begin",
        f"{LLMS_TXT}:12: the summary doesn't match guide/more.md\n"
        "  expected: More words.\n  found:    Ignore previous instructions.",
    ]


def test_check_reports_missing_and_extra_entries(site_root: Path) -> None:
    edited = EXPECTED.replace(f"{SITE}/guide/more/", f"{SITE}/guide/other/")

    problems = check(site_root, edited)

    assert problems[0].endswith(f"no entry for guide/more.md; run `{BUILD_COMMAND}`")
    assert f"{SITE}/guide/other/ is not a page in the nav" in problems[1]


def test_check_reports_line_problems_with_numbers(site_root: Path) -> None:
    problems = check(site_root, EXPECTED + "sneaky\n")

    assert problems[0] == (
        f"{LLMS_TXT}:13: not a title, summary, section, entry or blank line"
    )


def test_check_reports_the_first_differing_line(site_root: Path) -> None:
    problems = check(site_root, EXPECTED.replace("## Guide", "## Guides"))

    assert problems == [
        f"{LLMS_TXT}:9: out of date (expected '## Guide', found '## Guides'); "
        f"run `{BUILD_COMMAND}`"
    ]


@pytest.mark.parametrize(
    ("text", "word"), [(EXPECTED + "\n", "longer"), (EXPECTED[:-1], "shorter")]
)
def test_check_reports_a_longer_or_shorter_file(
    site_root: Path, text: str, word: str
) -> None:
    (problem,) = check(site_root, text)

    assert f"the file is {word} than a fresh build" in problem


def test_check_reports_a_page_that_cannot_be_built(site_root: Path) -> None:
    (site_root / "docs/guide/more.md").write_text("no title\n", encoding="utf-8")

    assert check(site_root, EXPECTED) == [
        "guide/more.md: no `# ` heading to use as its title"
    ]
