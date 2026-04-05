"""Tests for src/solidworks_mcp/agents/retrieval_index.py."""

from __future__ import annotations

import json
from pathlib import Path

from src.solidworks_mcp.agents.history_db import ErrorRecord, insert_error
from src.solidworks_mcp.agents.retrieval_index import build_local_retrieval_index


def test_build_local_retrieval_index_creates_file(tmp_path: Path) -> None:
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
    output_path = tmp_path / "retrieval" / "index.json"
    payload = build_local_retrieval_index(
        output_path=output_path,
        worked_examples_path=tmp_path / "missing-worked.md",
        tool_catalog_dir=tmp_path / "missing-tool-catalog",
        db_path=tmp_path / "missing-db.sqlite3",
    )

    assert output_path.exists()
    assert payload["stats"]["chunk_count"] == 0
