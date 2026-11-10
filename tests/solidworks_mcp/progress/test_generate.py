"""Generating the progress files (spec: docs/coverage-progress)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from solidworks_mcp.progress import generate
from solidworks_mcp.progress.com_coverage import (
    ComCoverage,
    InterfaceCoverage,
    Snapshot,
)
from solidworks_mcp.progress.snapshot import SNAPSHOT_PATH
from solidworks_mcp.tools.support_levels import SUPPORT_LEVELS, SupportLevel

_ROWS = [
    generate.ToolRow("a_tool", "modeling", SupportLevel.BETA, "x <y>.", "Does a."),
    generate.ToolRow("b_tool", "export", SupportLevel.STABLE, "", "Does b & c."),
]
_COVERAGE = ComCoverage(
    (
        InterfaceCoverage("IModelDoc2", ("GetTitle",), 4),
        InterfaceCoverage("ISketch", (), 0),
    ),
    1,
    9,
    "lib",
)


def _repo(tmp_path: Path) -> Path:
    """A minimal checkout: a snapshot and one adapter file."""
    snap = tmp_path / SNAPSHOT_PATH
    snap.parent.mkdir(parents=True)
    snap.write_text(
        Snapshot("lib", {"IModelDoc2": frozenset({"GetTitle", "Save3"})}).to_json(),
        encoding="utf-8",
    )
    adapters = tmp_path / "src/solidworks_mcp/adapters"
    adapters.mkdir(parents=True)
    (adapters / "a.py").write_text("model.GetTitle()", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_every_registered_tool_gets_a_row() -> None:
    rows = await generate.tool_rows()

    assert [r.name for r in rows] == sorted(SUPPORT_LEVELS)
    extrude = next(r for r in rows if r.name == "create_extrusion")
    assert extrude.family == "modeling"
    assert extrude.level is SupportLevel.STABLE
    assert extrude.summary.startswith("Extrude the sketch you just closed")
    assert "\n" not in extrude.summary


def test_the_data_counts_levels_and_lists_tools() -> None:
    data = json.loads(generate.progress_json(_ROWS, _COVERAGE))

    assert data["tools"]["total"] == 2
    assert data["tools"]["by_level"] == {
        "stable": 1,
        "beta": 1,
        "experimental": 0,
        "planned": 0,
    }
    assert data["tools"]["list"][0]["reason"] == "x <y>."
    assert data["com"]["core"] == {"covered": 1, "total": 4}
    assert data["com"]["api"] == {"covered": 1, "total": 9}
    assert data["com"]["interfaces"][0]["covered"] == ["GetTitle"]


def test_the_tables_carry_filters_and_escape_text() -> None:
    html = generate.tables_html(_ROWS, _COVERAGE)

    assert '<tr data-level="beta" data-family="modeling">' in html
    assert '<span class="level level-beta">beta</span>' in html
    assert "<small>x &lt;y&gt;.</small>" in html
    assert "Does b &amp; c." in html
    assert "<summary>25.0%</summary><small>GetTitle</small>" in html
    assert "<summary>0.0%</summary><small>none yet</small>" in html


def test_main_writes_every_output(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    written = generate.main(root)

    assert [p.name for p in written] == list(generate.OUTPUTS)
    data = json.loads((root / generate.OUTPUT_DIR / "progress.json").read_text())
    assert data["com"]["api"] == {"covered": 1, "total": 2}


def test_main_defaults_to_the_current_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(_repo(tmp_path))

    assert generate.main()[0] == tmp_path / generate.OUTPUT_DIR / "progress.svg"
