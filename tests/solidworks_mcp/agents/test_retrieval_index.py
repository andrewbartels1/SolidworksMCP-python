"""Tests for src/solidworks_mcp/agents/retrieval_index.py."""

from __future__ import annotations

import json
from pathlib import Path

from src.solidworks_mcp.agents.history_db import ErrorRecord, insert_error
from src.solidworks_mcp.agents.retrieval_index import (
    _chunk_text,
    _read_text,
    build_local_retrieval_index,
)


def test_build_local_retrieval_index_creates_file(tmp_path: Path) -> None:
    """Test build local retrieval index creates file."""

    worked_examples = tmp_path / "worked-examples.md"
    worked_examples.write_text(
        "## Example\nClassifier-first flow with feature-tree audit.",
        encoding="utf-8",
    )

    tool_catalog_dir = tmp_path / "tool-catalog"
    tool_catalog_dir.mkdir(parents=True)
    (tool_catalog_dir / "file-management.md").write_text(
        "# File Management\nTool docs chunk.",
        encoding="utf-8",
    )

    db_path = tmp_path / "agent_memory.sqlite3"
    insert_error(
        ErrorRecord(
            source="test",
            tool_name="classify_feature_tree",
            error_type="RecoverableFailure",
            error_message="bad input",
            root_cause="missing fields",
            remediation="provide required fields",
        ),
        db_path=db_path,
    )

    output_path = tmp_path / "retrieval" / "index.json"
    payload = build_local_retrieval_index(
        output_path=output_path,
        worked_examples_path=worked_examples,
        tool_catalog_dir=tool_catalog_dir,
        db_path=db_path,
    )

    assert output_path.exists()
    parsed = json.loads(output_path.read_text(encoding="utf-8"))
    assert parsed["version"] == "1.0"
    assert parsed["stats"]["chunk_count"] > 0
    assert len(parsed["chunks"]) == payload["stats"]["chunk_count"]


def test_build_local_retrieval_index_handles_missing_inputs(tmp_path: Path) -> None:
    """Test build local retrieval index handles missing inputs."""

    output_path = tmp_path / "retrieval" / "index.json"
    payload = build_local_retrieval_index(
        output_path=output_path,
        worked_examples_path=tmp_path / "missing-worked.md",
        tool_catalog_dir=tmp_path / "missing-tool-catalog",
        db_path=tmp_path / "missing-db.sqlite3",
    )

    assert output_path.exists()
    assert payload["stats"]["chunk_count"] == 0


def test_chunk_text_overlapping_chunks() -> None:
    """Test chunk text overlapping chunks."""

    text = "x" * 2400
    chunks = _chunk_text(text, chunk_size=1000, overlap=200)

    assert len(chunks) == 3
    assert len(chunks[0]) == 1000
    assert len(chunks[1]) == 1000
    assert len(chunks[2]) == 800


def test_read_text_oserror_returns_empty(monkeypatch, tmp_path: Path) -> None:
    """Test read text oserror returns empty."""

    path = tmp_path / "blocked.md"
    path.write_text("ignored", encoding="utf-8")

    def _raise_oserror(*args, **kwargs):
        """Test raise oserror."""

        raise OSError("cannot read")

    monkeypatch.setattr(Path, "read_text", _raise_oserror)
    assert _read_text(path) == ""


def test_build_local_retrieval_index_uses_defaults_and_skips_index_md(
    tmp_path: Path, monkeypatch
) -> None:
    """Test build local retrieval index uses defaults and skips index md."""

    monkeypatch.chdir(tmp_path)

    worked_examples = tmp_path / "docs" / "user-guide" / "worked-examples.md"
    worked_examples.parent.mkdir(parents=True, exist_ok=True)
    worked_examples.write_text("worked example", encoding="utf-8")

    tool_catalog = tmp_path / "docs" / "user-guide" / "tool-catalog"
    tool_catalog.mkdir(parents=True, exist_ok=True)
    (tool_catalog / "index.md").write_text("skip me", encoding="utf-8")
    (tool_catalog / "modeling.md").write_text("use me", encoding="utf-8")

    payload = build_local_retrieval_index()

    output_path = tmp_path / ".solidworks_mcp" / "retrieval" / "local_index.json"
    assert output_path.exists()
    assert payload["stats"]["worked_examples_source"].endswith("worked-examples.md")
    assert payload["stats"]["tool_catalog_source"].endswith("tool-catalog")
    assert any(c["source"].endswith("modeling.md") for c in payload["chunks"])
    assert not any(c["source"].endswith("index.md") for c in payload["chunks"])
