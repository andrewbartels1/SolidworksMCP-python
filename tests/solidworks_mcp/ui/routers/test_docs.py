"""Tests for docs router endpoints."""

from __future__ import annotations

import pytest

from solidworks_mcp.ui.routers import docs as docs_router


@pytest.mark.asyncio
async def test_docs_context_calls_service(monkeypatch) -> None:
    """docs_context should call fetch_docs_context."""
    # Patch the service call to return a sentinel response.
    monkeypatch.setattr(
        docs_router, "fetch_docs_context", lambda *_a, **_kw: {"ok": True}
    )
    payload = docs_router.DocsContextRequest(session_id="s1", query="query")
    result = await docs_router.docs_context(payload)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_rag_ingest_calls_service(monkeypatch) -> None:
    """rag_ingest should call ingest_reference_source."""
    # Patch the service call to return a sentinel response.
    monkeypatch.setattr(
        docs_router, "ingest_reference_source", lambda *_a, **_kw: {"ingested": True}
    )
    payload = docs_router.RagIngestRequest(
        session_id="s1",
        source_path="C:/tmp/doc.txt",
        namespace="ns",
        chunk_size=100,
        overlap=10,
    )
    result = await docs_router.rag_ingest(payload)
    assert result == {"ingested": True}
