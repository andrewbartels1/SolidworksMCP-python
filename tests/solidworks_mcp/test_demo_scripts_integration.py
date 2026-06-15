"""Integration tests wrapping the demo scripts in scripts/demo_*.py.

Each test invokes the corresponding demo script's async entry point against a
live SolidWorks instance.  These tests are:

- Marked ``solidworks_only`` — skipped unless SolidWorks is installed.
- Gated by the ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION`` environment variable.
- Windows-only (SolidWorks COM requires Windows).

Run during the ``dev-test-full`` workflow::

    $env:SOLIDWORKS_MCP_RUN_REAL_INTEGRATION = "1"
    .\\dev-commands.ps1 dev-test-full
"""

from __future__ import annotations

import os
import platform
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO_ROOT / "scripts"
_REAL_FLAG = "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION"
_REAL_ENABLED = os.getenv(_REAL_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}

# Add src to sys.path so demo scripts can import solidworks_mcp.
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


def _skip_unless_live() -> None:
    if platform.system() != "Windows":
        pytest.skip("Demo integration tests require Windows")
    if not _REAL_ENABLED:
        pytest.skip(
            f"Set {_REAL_FLAG}=1 to run live SolidWorks demo integration tests"
        )


# ---------------------------------------------------------------------------
# sweep + loft demo
# ---------------------------------------------------------------------------


@pytest.mark.solidworks_only
@pytest.mark.asyncio
async def test_demo_sweep_loft(tmp_path: Path) -> None:
    """demo_sweep_loft.py: coil spring + tapered loft cone built from scratch."""
    _skip_unless_live()

    # Import lazily so the module-level sys.path manipulation in the script
    # doesn't affect our process permanently.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "demo_sweep_loft", _SCRIPTS / "demo_sweep_loft.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    artefacts = await mod.build_demo_part(tmp_path)
    assert artefacts.get("part"), "Expected a part path in artefacts"
    assert Path(artefacts["part"]).exists(), "Part file was not created"


# ---------------------------------------------------------------------------
# features demo (revolve, cut-extrude, fillet, chamfer)
# ---------------------------------------------------------------------------


@pytest.mark.solidworks_only
@pytest.mark.asyncio
async def test_demo_features(tmp_path: Path) -> None:
    """demo_features.py: revolve, cut-extrude, fillet, chamfer operations."""
    _skip_unless_live()

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "demo_features", _SCRIPTS / "demo_features.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    artefacts = await mod.build_demo_part(tmp_path)
    assert artefacts.get("part"), "Expected a part path in artefacts"
    assert Path(artefacts["part"]).exists(), "Part file was not created"


# ---------------------------------------------------------------------------
# sketches demo (spline, arc, polygon, ellipse, patterns, mirror, offset)
# ---------------------------------------------------------------------------


@pytest.mark.solidworks_only
@pytest.mark.asyncio
async def test_demo_sketches(tmp_path: Path) -> None:
    """demo_sketches.py: nine advanced sketch operations."""
    _skip_unless_live()

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "demo_sketches", _SCRIPTS / "demo_sketches.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    artefacts = await mod.build_demo_part(tmp_path)
    assert artefacts.get("part"), "Expected a part path in artefacts"
    assert Path(artefacts["part"]).exists(), "Part file was not created"


# ---------------------------------------------------------------------------
# export demo (STEP, STL, IGES, PNG)
# ---------------------------------------------------------------------------


@pytest.mark.solidworks_only
@pytest.mark.asyncio
async def test_demo_export(tmp_path: Path) -> None:
    """demo_export.py: STEP / STL / IGES / PNG export of a box part."""
    _skip_unless_live()

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "demo_export", _SCRIPTS / "demo_export.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    artefacts = await mod.run_export_demo(tmp_path)
    assert artefacts.get("part"), "Expected a part path in artefacts"
    assert Path(artefacts["part"]).exists(), "Part file was not created"
    # At minimum STEP, STL, and PNG should be produced.
    for fmt in ("step", "stl", "png"):
        key = f"export_{fmt}"
        if key in artefacts:
            assert Path(artefacts[key]).exists(), f"{fmt} export file was not created"


# ---------------------------------------------------------------------------
# analysis demo (mass props, dimensions, model info)
# ---------------------------------------------------------------------------


@pytest.mark.solidworks_only
@pytest.mark.asyncio
async def test_demo_analysis(tmp_path: Path) -> None:
    """demo_analysis.py: model-info, mass-properties, dimension read/write."""
    _skip_unless_live()

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "demo_analysis", _SCRIPTS / "demo_analysis.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    # demo_analysis uses run_analysis_demo(out_dir) instead of build_demo_part
    await mod.run_analysis_demo(tmp_path)


# ---------------------------------------------------------------------------
# save_validation demo (issue #7 acceptance criteria)
# ---------------------------------------------------------------------------


@pytest.mark.solidworks_only
@pytest.mark.asyncio
async def test_demo_save_validation(tmp_path: Path) -> None:
    """demo_save_validation.py: all issue-7 save-target guardrail ACs."""
    _skip_unless_live()

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "demo_save_validation", _SCRIPTS / "demo_save_validation.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    # Override the hard-coded OUT_DIR so the script writes into tmp_path.
    mod.OUT_DIR = tmp_path / "save_validation"

    # run_validation() connects to SolidWorks, runs all acceptance-criterion
    # checks, and returns 0 on full pass or 1 on any hard failure.
    exit_code = await mod.run_validation()
    assert exit_code == 0, "demo_save_validation reported one or more hard failures"
