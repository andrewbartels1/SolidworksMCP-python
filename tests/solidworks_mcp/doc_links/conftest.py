"""A small docs site on disk for the ``doc_links`` tests."""

from __future__ import annotations

from pathlib import Path

import pytest

SITE = "https://example.github.io/proj"
REPO = "https://github.com/owner/proj"

MKDOCS = f"""\
site_name: Proj
site_url: {SITE}/
site_description: A test project
repo_url: {REPO}
markdown_extensions:
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          format: !!python/name:pymdownx.superfences.fence_code_format
nav:
  - Home: index.md
  - Guide:
      - Start: guide/start.md
      - Deeper:
          - More: guide/more.md
      - Missing: guide/missing.md
  - API Reference: api/
"""

PAGES = {
    "index.md": "# Proj\n\nProj does a thing. See [the guide](guide/start.md).\n",
    "guide/start.md": (
        "---\ntitle: x\n---\n# Start here {#top}\n\n> A note first.\n\n"
        "Start with `uv`, then\nread [more](more.md#details).\n\n## Details\n"
    ),
    "guide/more.md": "# More\n\nMore words.\n\n## Details\n\n## Details\n",
}


def write_site(root: Path, pages: dict[str, str] | None = None) -> Path:
    """Write ``mkdocs.yml`` and the pages under ``root``; return ``root``."""
    (root / "mkdocs.yml").write_text(MKDOCS, encoding="utf-8")
    for name, text in (PAGES if pages is None else pages).items():
        path = root / "docs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


@pytest.fixture
def site_root(tmp_path: Path) -> Path:
    """A repository root holding the small site."""
    return write_site(tmp_path)
