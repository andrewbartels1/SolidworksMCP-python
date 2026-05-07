"""Docs context fetching and RAG ingestion for the Prefab CAD dashboard.

Responsibilities (Single Responsibility principle):
- Fetch and filter docs from the MCP docs endpoint (``fetch_docs_context``).
- Ingest local files or URLs into the simple retrieval index (``ingest_reference_source``).

Does NOT own: LLM calls, preview export, session state mutation beyond metadata merges.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from loguru import logger

from ...agents.history_db import insert_evidence_link, insert_tool_call_record
from ...agents.retrieval_index import _chunk_text
from ._utils import (
    DEFAULT_API_ORIGIN,
    DEFAULT_RAG_DIR,
    HTMLTextExtractor,
    filter_docs_text,
    is_url_reference,
    merge_metadata,
    persist_ui_action,
    read_reference_source,
    read_reference_url,
    sanitize_ui_text,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_docs_context(
    session_id: str,
    *,
    docs_query: str = "",
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Fetch docs text from the ``/docs`` endpoint and store a filtered context snippet.

    Args:
        session_id: Dashboard session identifier.
        docs_query: Keyword(s) to filter the docs text by.
        db_path: Optional override for the SQLite database path.
        api_origin: Base URL of the running FastAPI server.

    Returns:
        Full dashboard state payload.
    """
    from .session_service import build_dashboard_state, ensure_dashboard_session  # noqa: PLC0415

    ensure_dashboard_session(session_id, db_path=db_path)
    docs_url = f"{api_origin}/docs"
    query_text = sanitize_ui_text(docs_query, "solidworks workflow")
    try:
        request = Request(docs_url, headers={"User-Agent": "solidworks-mcp-ui/1.0"})
        with urlopen(request, timeout=8) as response:
            html = response.read().decode("utf-8", errors="ignore")
        extractor = HTMLTextExtractor()
        extractor.feed(html)
        snippet = filter_docs_text(extractor.text(), query_text)
        persist_ui_action(
            session_id,
            tool_name="ui.docs.fetch",
            db_path=db_path,
            metadata_updates={
                "docs_query": query_text,
                "docs_context_text": snippet,
                "latest_message": "Docs context updated from MCP docs endpoint.",
                "latest_error_text": "",
                "remediation_hint": "",
            },
            input_payload={"query": query_text, "url": docs_url},
            output_payload={"chars": len(snippet)},
        )
    except Exception as exc:
        logger.exception("[ui.fetch_docs_context] failed session_id={}", session_id)
        merge_metadata(
            session_id,
            db_path=db_path,
            docs_query=query_text,
            docs_context_text="",
            latest_error_text=str(exc),
            remediation_hint="Verify the /docs endpoint is reachable, then retry docs refresh.",
        )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


def ingest_reference_source(
    session_id: str,
    *,
    source_path: str,
    namespace: str,
    chunk_size: int = 1200,
    overlap: int = 200,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Ingest a local file or URL into the simple local retrieval index.

    Args:
        session_id: Dashboard session identifier.
        source_path: Absolute file path or http/https URL.
        namespace: Namespace key that isolates this index from others.
        chunk_size: Maximum characters per chunk.
        overlap: Overlapping characters between adjacent chunks.
        db_path: Optional override for the SQLite database path.

    Returns:
        Full dashboard state payload.
    """
    from .session_service import build_dashboard_state, ensure_dashboard_session  # noqa: PLC0415

    ensure_dashboard_session(session_id, db_path=db_path)
    source_reference = (source_path or "").strip()
    resolved_namespace = (
        namespace or "engineering-reference"
    ).strip() or "engineering-reference"

    try:
        if is_url_reference(source_reference):
            source_identifier = source_reference
            source_text, source_label = read_reference_url(source_reference)
        else:
            resolved_source = Path(source_reference).expanduser()
            if not resolved_source.exists():
                merge_metadata(
                    session_id,
                    db_path=db_path,
                    rag_source_path=str(resolved_source),
                    rag_namespace=resolved_namespace,
                    rag_status="Reference source path was not found.",
                    latest_error_text=f"Missing reference source: {resolved_source}",
                    remediation_hint=(
                        "Provide an absolute path or an http/https URL for a PDF, "
                        "markdown, text, or HTML source."
                    ),
                )
                return build_dashboard_state(session_id, db_path=db_path)
            source_identifier = str(resolved_source.resolve())
            source_label = resolved_source.name
            source_text = read_reference_source(resolved_source)

        chunks = _chunk_text(source_text, chunk_size=chunk_size, overlap=overlap)
        output_path = DEFAULT_RAG_DIR / f"{resolved_namespace}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "1.0",
            "namespace": resolved_namespace,
            "source_location": source_identifier,
            "chunk_count": len(chunks),
            "chunks": [
                {
                    "id": f"{resolved_namespace}-{index}",
                    "source": source_identifier,
                    "text": chunk,
                }
                for index, chunk in enumerate(chunks, start=1)
            ],
        }
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
        )

        # --- FAISS vector index (best-effort; skipped if optional deps missing) ---
        try:
            from ...agents.vector_rag import VectorRAGIndex  # noqa: PLC0415

            idx = VectorRAGIndex.load(
                namespace=resolved_namespace, rag_dir=DEFAULT_RAG_DIR
            )
            for chunk in payload["chunks"]:
                idx.ingest_text(
                    chunk["text"], source=source_identifier, tags=[resolved_namespace]
                )
            idx.save()
            logger.info(
                "[ui.ingest_reference_source] FAISS index updated namespace={} chunks={}",
                resolved_namespace,
                len(chunks),
            )
        except ImportError:
            logger.debug(
                "[ui.ingest_reference_source] FAISS not available; skipping vector index"
            )
        except Exception as faiss_exc:
            logger.warning(
                "[ui.ingest_reference_source] FAISS indexing failed (non-fatal): {}",
                faiss_exc,
            )

        insert_evidence_link(
            session_id=session_id,
            source_type="rag_ingest",
            source_id=source_identifier,
            relevance_score=0.88,
            rationale=f"Ingested {len(chunks)} chunk(s) into namespace '{resolved_namespace}'.",
            payload_json=json.dumps(
                {
                    "namespace": resolved_namespace,
                    "index_path": str(output_path.resolve()),
                    "chunk_count": len(chunks),
                },
                ensure_ascii=True,
            ),
            db_path=db_path,
        )
        merge_metadata(
            session_id,
            db_path=db_path,
            rag_source_path=source_identifier,
            rag_namespace=resolved_namespace,
            rag_status=f"Ingested {len(chunks)} chunk(s) from {source_label}.",
            rag_index_path=str(output_path.resolve()),
            rag_chunk_count=len(chunks),
            rag_provenance_text=(
                f"Namespace {resolved_namespace} | source {source_label} | chunks {len(chunks)}"
            ),
            latest_message=f"Reference source {source_label} ingested for retrieval.",
            latest_error_text="",
            remediation_hint="",
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.ingest_reference_source",
            input_json=json.dumps(
                {
                    "source_path": source_identifier,
                    "namespace": resolved_namespace,
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                },
                ensure_ascii=True,
            ),
            output_json=json.dumps(
                {"index_path": str(output_path.resolve()), "chunk_count": len(chunks)},
                ensure_ascii=True,
            ),
            success=True,
            db_path=db_path,
        )
    except Exception as exc:
        merge_metadata(
            session_id,
            db_path=db_path,
            rag_source_path=source_reference,
            rag_namespace=resolved_namespace,
            rag_status="Reference ingestion failed.",
            latest_error_text=str(exc),
            remediation_hint=(
                "Use a readable local file or http/https URL and ensure optional "
                "PDF dependencies are installed."
            ),
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.ingest_reference_source",
            input_json=json.dumps(
                {"source_path": source_reference, "namespace": resolved_namespace},
                ensure_ascii=True,
            ),
            output_json=json.dumps({"error": str(exc)}, ensure_ascii=True),
            success=False,
            db_path=db_path,
        )

    return build_dashboard_state(session_id, db_path=db_path)
