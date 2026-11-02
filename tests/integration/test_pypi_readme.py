"""The PyPI description: the README with every relative link made absolute.

PyPI shows the README without the repository around it, so the build hook in
``pyproject.toml`` rewrites relative image sources and links. These tests
render the description the way the build does and check the result.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RAW = "https://raw.githubusercontent.com/andrewbartels1/SolidworksMCP-python/main/"
BLOB = "https://github.com/andrewbartels1/SolidworksMCP-python/blob/main/"


@pytest.fixture(scope="module")
def description(tmp_path_factory: pytest.TempPathFactory) -> str:
    """The package description, rendered by the build hook's own CLI."""
    out = tmp_path_factory.mktemp("pypi") / "README.md"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "hatch_fancy_pypi_readme",
            "pyproject.toml",
            "-o",
            str(out),
        ],
        cwd=ROOT,
        check=True,
        # The README has symbols the Windows console code page can't encode.
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    return out.read_text(encoding="utf-8")


def test_no_relative_image_or_link_is_left(description: str) -> None:
    relative = re.findall(
        r'\]\((?!https?://|#|mailto:)[^)\s]+\)|(?:src|href)="(?!https?://|#|mailto:)[^"]+"',
        description,
    )

    assert relative == []


def test_images_load_the_raw_file(description: str) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    image = re.search(r'src="(docs/[^"]+\.gif)"', readme)

    assert image, "the README shows at least one demo GIF from docs/"
    assert f'src="{RAW}{image[1]}"' in description


def test_file_links_open_on_github(description: str) -> None:
    assert f"]({BLOB}README.es-ES.md)" in description


def test_absolute_urls_and_anchors_are_untouched(description: str) -> None:
    assert "](https://andrewbartels1.github.io/SolidworksMCP-python/" in description
    assert (
        "https://github.com/andrewbartels1/SolidworksMCP-python/blob/main/https"
        not in description
    )


def test_the_registry_marker_survives(description: str) -> None:
    assert "mcp-name: io.github.andrewbartels1/solidworks-mcp-python" in description
