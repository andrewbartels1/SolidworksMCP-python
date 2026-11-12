"""Tests for reading file paths out of GetDependencies2's reply."""

from __future__ import annotations

from pathlib import Path

from solidworks_mcp.utils.sw_dependencies import dependency_paths


def test_names_and_paths_alternate_and_only_paths_are_kept() -> None:
    raw = ("plate", r"C:\work\plate.SLDPRT", "pin", r"C:\work\pin.sldprt")

    assert dependency_paths(raw) == [
        Path(r"C:\work\plate.SLDPRT"),
        Path(r"C:\work\pin.sldprt"),
    ]


def test_a_repeated_path_is_kept_once_ignoring_case(tmp_path) -> None:
    part = str(tmp_path / "plate.SLDPRT")
    raw = [part, str(tmp_path / "sub.sldasm"), part]

    assert dependency_paths(raw) == [Path(part), tmp_path / "sub.sldasm"]


def test_other_entries_are_skipped() -> None:
    """Bare names, other file types and non-strings give nothing."""
    raw = ("plate.SLDPRT", r"C:\work\notes.txt", 42, None, r"C:\work\d.SLDDRW")

    assert dependency_paths(raw) == [Path(r"C:\work\d.SLDDRW")]


def test_a_reply_that_is_not_a_list_gives_nothing() -> None:
    assert dependency_paths(None) == []
    assert dependency_paths(r"C:\work\plate.SLDPRT") == []
