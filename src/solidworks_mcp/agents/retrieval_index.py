"""Local retrieval index builder for feature-tree audits, tool docs, and failures."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .history_db import DEFAULT_DB_PATH, find_recent_errors


def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    """Split long text into overlapping chunks for simple local retrieval."""
    normalized = (text or "").strip()
    if not normalized:
        return []

    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(0, end - overlap)
    return chunks


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_local_retrieval_index(
    *,
    output_path: Path | None = None,
    worked_examples_path: Path | None = None,
    tool_catalog_dir: Path | None = None,
    db_path: Path | None = None,
    max_recent_errors: int = 200,
) -> dict[str, Any]:
    """Build a JSON retrieval index from local audits, tool docs, and failures."""
    if output_path is None:
        output_path = Path(".solidworks_mcp") / "retrieval" / "local_index.json"
    if worked_examples_path is None:
        worked_examples_path = Path("docs") / "user-guide" / "worked-examples.md"
    if tool_catalog_dir is None:
        tool_catalog_dir = Path("docs") / "user-guide" / "tool-catalog"
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    chunks: list[dict[str, Any]] = []
    chunk_id = 0

    worked_text = _read_text(worked_examples_path)
    for idx, chunk in enumerate(_chunk_text(worked_text), start=1):
        chunk_id += 1
        chunks.append(
            {
                "id": f"audit-worked-examples-{idx}",
                "chunk_id": chunk_id,
                "source_type": "feature_tree_audit",
                "source": str(worked_examples_path),
                "text": chunk,
                "tags": ["audit", "worked_examples", "inspect_classify_delegate"],
            }
        )

    if tool_catalog_dir.exists():
        for doc_path in sorted(tool_catalog_dir.glob("*.md")):
            if doc_path.name.lower() == "index.md":
                continue
            doc_text = _read_text(doc_path)
            for idx, chunk in enumerate(_chunk_text(doc_text), start=1):
                chunk_id += 1
                chunks.append(
                    {
                        "id": f"tool-doc-{doc_path.stem}-{idx}",
                        "chunk_id": chunk_id,
                        "source_type": "tool_doc",
                        "source": str(doc_path),
                        "text": chunk,
                        "tags": ["tool_catalog", doc_path.stem],
                    }
                )

    for idx, error in enumerate(
        find_recent_errors(limit=max_recent_errors, db_path=db_path),
        start=1,
    ):
        chunk_id += 1
        error_text = (
            f"source={error.get('source')} | tool={error.get('tool_name')} | "
            f"type={error.get('error_type')} | message={error.get('error_message')} | "
            f"root_cause={error.get('root_cause')} | remediation={error.get('remediation')}"
        )
        chunks.append(
            {
                "id": f"failure-memory-{idx}",
                "chunk_id": chunk_id,
                "source_type": "failure_memory",
                "source": str(db_path),
                "text": error_text,
                "tags": ["failure_memory", error.get("tool_name", "unknown")],
                "created_at": error.get("created_at"),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "stats": {
            "chunk_count": len(chunks),
            "worked_examples_source": str(worked_examples_path),
            "tool_catalog_source": str(tool_catalog_dir),
            "failure_memory_source": str(db_path),
        },
        "chunks": chunks,
    }

    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    return payload
