"""Docs context and RAG ingestion routes for the Prefab CAD dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import DEFAULT_SESSION_ID, fetch_docs_context, ingest_reference_source

router = APIRouter()


class DocsContextRequest(BaseModel):
    """Request payload for docs-context refresh."""

    session_id: str = DEFAULT_SESSION_ID
    query: str = "SolidWorks MCP endpoints"


class RagIngestRequest(BaseModel):
    """Request payload for BYO retrieval ingestion from a local path or URL."""

    session_id: str = DEFAULT_SESSION_ID
    source_path: str
    namespace: str = "engineering-reference"
    chunk_size: int = 1200
    overlap: int = 200


@router.post("/api/ui/docs/context")
async def docs_context(payload: DocsContextRequest) -> dict[str, Any]:
    """Fetch and cache docs text from the /docs endpoint."""
    return fetch_docs_context(payload.session_id, docs_query=payload.query)


@router.post("/api/ui/rag/ingest")
async def rag_ingest(payload: RagIngestRequest) -> dict[str, Any]:
    """Ingest a local file or URL into the local retrieval index."""
    return ingest_reference_source(
        payload.session_id,
        source_path=payload.source_path,
        namespace=payload.namespace,
        chunk_size=payload.chunk_size,
        overlap=payload.overlap,
    )
