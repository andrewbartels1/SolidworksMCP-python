"""The progress image (spec: docs/coverage-progress)."""

from __future__ import annotations

from xml.etree import ElementTree

from solidworks_mcp.progress.com_coverage import ComCoverage, InterfaceCoverage
from solidworks_mcp.progress.svg import LEVEL_COLOURS, render
from solidworks_mcp.tools.support_levels import SupportLevel

_COVERAGE = ComCoverage(
    (InterfaceCoverage("IModelDoc2", ("GetTitle",), 4),), 3, 12, "lib"
)
_LEVELS = {
    SupportLevel.STABLE: 6,
    SupportLevel.BETA: 2,
    SupportLevel.EXPERIMENTAL: 1,
    SupportLevel.PLANNED: 1,
}


def test_the_image_is_valid_svg_with_its_own_dark_panel() -> None:
    svg = render(_LEVELS, _COVERAGE)

    root = ElementTree.fromstring(svg)
    assert root.tag.endswith("svg")
    assert 'fill="url(#panel)"' in svg


def test_the_image_states_the_counts_as_text() -> None:
    svg = render(_LEVELS, _COVERAGE)

    for text in (
        "MCP tools: 10",
        "80% work on SolidWorks today",
        "stable 6",
        "planned 1",
        "1 of 4 methods · 25.0%",
        "Whole API: 3 of 12 method names (25.0%)",
    ):
        assert text in svg, text


def test_each_level_below_planned_fills_its_share_of_the_bar() -> None:
    svg = render(_LEVELS, _COVERAGE)

    # 784 px track: stable 6/10, beta 2/10, experimental 1/10.
    assert (
        f'width="470.4" height="24" fill="{LEVEL_COLOURS[SupportLevel.STABLE]}"' in svg
    )
    assert f'width="156.8" height="24" fill="{LEVEL_COLOURS[SupportLevel.BETA]}"' in svg
    assert 'x="655.2" y="54" width="78.4"' in svg


def test_an_empty_project_draws_empty_bars() -> None:
    svg = render({}, ComCoverage((), 0, 0, "lib"))

    assert "MCP tools: 0" in svg
    assert "0 of 0 methods · 0.0%" in svg
