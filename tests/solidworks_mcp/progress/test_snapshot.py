"""Refreshing the type-library snapshot (spec: docs/coverage-progress)."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.adapters import sw_type_info
from solidworks_mcp.progress import snapshot
from solidworks_mcp.progress.com_coverage import Snapshot


def test_the_snapshot_records_the_library_and_its_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        sw_type_info, "type_library_name", lambda: "win32com.gen_py.IIDx0x34x0"
    )
    monkeypatch.setattr(
        sw_type_info,
        "all_interface_methods",
        lambda: {"IFeature": frozenset({"GetNextFeature"})},
    )

    path = snapshot.main(tmp_path)

    assert path == tmp_path / snapshot.SNAPSHOT_PATH
    assert Snapshot.load(path) == Snapshot(
        "IIDx0x34x0", {"IFeature": frozenset({"GetNextFeature"})}
    )


def test_main_defaults_to_the_current_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sw_type_info, "type_library_name", lambda: "gen_py.L")
    monkeypatch.setattr(sw_type_info, "all_interface_methods", dict)

    assert snapshot.main() == tmp_path / snapshot.SNAPSHOT_PATH


def test_without_the_type_library_it_says_where_to_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sw_type_info, "type_library_name", lambda: None)

    with pytest.raises(RuntimeError, match="Windows with SolidWorks"):
        snapshot.take_snapshot()
