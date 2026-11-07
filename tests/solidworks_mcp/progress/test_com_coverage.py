"""COM coverage counted from a snapshot and a source scan (spec: docs/coverage-progress)."""

from __future__ import annotations

from pathlib import Path

from solidworks_mcp.progress.com_coverage import (
    CORE_INTERFACES,
    Snapshot,
    adapter_sources,
    called_names,
    measure,
)

_SNAPSHOT = Snapshot(
    "lib-x0x34x0",
    {
        "IModelDoc2": frozenset({"ForceRebuild3", "GetTitle", "EditUndo2"}),
        "IFeature": frozenset({"GetNextFeature", "GetTitle"}),
        "IOther": frozenset({"Obscure"}),
    },
)


def test_names_used_as_attributes_or_strings_are_found() -> None:
    source = 'model.ForceRebuild3(True)\nflag_members(obj, "EditUndo2")\nx.lower()'

    assert called_names([source]) == {"ForceRebuild3", "EditUndo2"}


def test_coverage_counts_core_interfaces_and_the_whole_api() -> None:
    coverage = measure(_SNAPSHOT, {"ForceRebuild3", "GetTitle", "NotInTheApi"})

    by_name = {i.name: i for i in coverage.interfaces}
    assert [i.name for i in coverage.interfaces] == list(CORE_INTERFACES)
    assert by_name["IModelDoc2"].covered == ("ForceRebuild3", "GetTitle")
    assert by_name["IModelDoc2"].total == 3
    assert by_name["ISketch"].total == 0
    assert (coverage.core_covered, coverage.core_total) == (3, 5)
    # Distinct names: ForceRebuild3, GetTitle, EditUndo2, GetNextFeature, Obscure.
    assert (coverage.api_covered, coverage.api_total) == (2, 5)
    assert coverage.type_library == "lib-x0x34x0"


def test_the_snapshot_round_trips_through_its_file(tmp_path: Path) -> None:
    path = tmp_path / "snap.json"
    path.write_text(_SNAPSHOT.to_json(), encoding="utf-8")

    assert Snapshot.load(path) == _SNAPSHOT
    assert '  "IFeature": ["GetNextFeature", "GetTitle"],' in _SNAPSHOT.to_json()


def test_adapter_sources_reads_every_file_below(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.py").write_text("A", encoding="utf-8")
    (tmp_path / "sub" / "b.py").write_text("B", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("C", encoding="utf-8")

    assert adapter_sources(tmp_path) == ["A", "B"]
