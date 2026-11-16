"""The committed llms.txt matches the docs, and every project link resolves.

Specs: docs/llms-txt and docs/link-check (the offline half). Editing a
page's title or opening paragraph, or the nav, changes ``docs/llms.txt``;
rebuild it with ``python -m solidworks_mcp.doc_links build``.
"""

from __future__ import annotations

from pathlib import Path

from solidworks_mcp.doc_links.links import all_links, check_internal
from solidworks_mcp.doc_links.llms_txt import check
from solidworks_mcp.doc_links.pages import load_site

_ROOT = Path(__file__).resolve().parents[2]


def test_llms_txt_matches_the_docs_word_for_word() -> None:
    problems = check(_ROOT)

    assert problems == [], "\n".join(problems)


def test_every_link_within_the_project_resolves() -> None:
    problems = check_internal(_ROOT, load_site(_ROOT), all_links(_ROOT))

    assert problems == [], "\n".join(problems)
