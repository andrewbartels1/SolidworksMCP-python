"""Tests for the shared filesystem-facts helper."""

from __future__ import annotations

import hashlib
from pathlib import Path

from solidworks_mcp.tools.file_facts import file_fact_snapshot


def test_empty_path_is_none() -> None:
    assert file_fact_snapshot("") is None


def test_missing_file_and_directories_are_none(tmp_path: Path) -> None:
    assert file_fact_snapshot(str(tmp_path / "absent.slddrw")) is None
    assert file_fact_snapshot(str(tmp_path)) is None


def test_existing_file_reports_size_mtime_and_hash(tmp_path: Path) -> None:
    target = tmp_path / "part.sldprt"
    target.write_bytes(b"solid")

    facts = file_fact_snapshot(str(target))

    assert facts == {
        "path": str(target),
        "size_bytes": 5,
        "modified_time": target.stat().st_mtime,
        "sha256": hashlib.sha256(b"solid").hexdigest(),
    }
