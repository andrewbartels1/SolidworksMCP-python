"""Tests for solidworks_mcp.ui.services.docs_service."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.ui.services.docs_service import fetch_docs_context


def test_fetch_docs_context_rejects_non_http_origins(tmp_path: Path) -> None:
    """Only http(s) docs endpoints are fetched (no file:// or ftp:// reads)."""
    with pytest.raises(ValueError, match="Disallowed URL scheme in docs endpoint"):
        fetch_docs_context(
            "s1", db_path=tmp_path / "db.sqlite3", api_origin="file:///etc"
        )


def test_docs_service_ingest_saves_index(monkeypatch, tmp_path):
    """ingest_reference_source should call idx.save() after ingesting. Covers lines 183-184."""
    from solidworks_mcp.ui.services import docs_service

    save_calls: list = []
    ingest_calls: list = []

    class _FakeIndex:
        def ingest_text(self, text, source=None, tags=None):
            ingest_calls.append({"text": text, "source": source})

        def save(self):
            save_calls.append(True)

        @classmethod
        def load(cls, namespace=None, rag_dir=None):
            return cls()

    # Patch the inline import by setting it on the vector_rag module
    from solidworks_mcp.agents import vector_rag

    monkeypatch.setattr(vector_rag, "VectorRAGIndex", _FakeIndex)

    monkeypatch.setattr(
        docs_service,
        "ensure_dashboard_session"
        if hasattr(docs_service, "ensure_dashboard_session")
        else "__missing__",
        lambda *_a, **_kw: None,
        raising=False,
    )

    # Create a real markdown file to ingest
    md_file = tmp_path / "test.md"
    md_file.write_text("# Test\nHello world content for RAG.", encoding="utf-8")

    # Patch ensure_dashboard_session and build_dashboard_state
    monkeypatch.setattr(
        "solidworks_mcp.ui.services.session_service.ensure_dashboard_session",
        lambda *_a, **_kw: None,
    )
    monkeypatch.setattr(
        "solidworks_mcp.ui.services.session_service.build_dashboard_state",
        lambda *_a, **_kw: {"ok": True},
    )
    monkeypatch.setattr(docs_service, "DEFAULT_RAG_DIR", tmp_path)
    # Avoid DB writes from insert_tool_call_record
    monkeypatch.setattr(docs_service, "insert_tool_call_record", lambda **_kw: None)

    docs_service.ingest_reference_source(
        "s1",
        source_path=str(md_file),
        namespace="test-ns",
    )

    assert len(save_calls) == 1
    assert len(ingest_calls) >= 1
