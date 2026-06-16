"""FastAPI backend for the Prefab CAD assistant dashboard.

REST API endpoints for dashboard actions: - GET /api/ui/state - Hydrate UI with current
session state - POST /api/ui/brief/approve - Accept user goal - POST /api/ui/clarify -
Call GitHub Copilot to generate Q&A - POST /api/ui/family/inspect - Call GitHub Copilot
to classify design family - POST /api/ui/family/accept - Accept proposed family - POST
/api/ui/checkpoints/execute-next - Execute next checkpoint (adapter-backed; unsupported
tools marked MOCKED) - POST /api/ui/preview/refresh - Sync 3D view from SolidWorks
export_image - POST /api/ui/manual-sync/reconcile - Detect manual edits via snapshot
diff - GET /previews/* - Serve static PNG preview images - GET /docs - FastAPI OpenAPI
UI for local endpoint inspection

LLM Integration: - Clarify button: GitHub Copilot (default: github:openai/gpt-4.1) -
Inspect button: GitHub Copilot family classification - Requires: GH_TOKEN or
GITHUB_API_KEY environment variable with models:read scope
"""

from __future__ import annotations

import json
import time
from pathlib import Path as FilePath
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from .routers import checkpoint as checkpoint_router
from .routers import docs as docs_router
from .routers import llm as llm_router
from .routers import local_model as local_model_router
from .routers import model as model_router
from .routers import preview as preview_router
from .routers import session as session_router
from .routers import viewer as viewer_router
from .services import (  # noqa: F401  (re-exported for monkeypatching in tests)
    DEFAULT_API_ORIGIN,
    DEFAULT_SESSION_ID,
    accept_family_choice,
    approve_design_brief,
    build_dashboard_state,
    build_dashboard_trace_payload,
    connect_target_model,
    ensure_preview_dir,
    execute_next_checkpoint,
    ingest_reference_source,
    inspect_family,
    reconcile_manual_edits,
    refresh_preview,
    request_clarifications,
    select_workflow_mode,
    update_ui_preferences,
)

UI_LOG_DIR = FilePath(".solidworks_mcp") / "ui_logs"
UI_HTTP_LOG_FILE = UI_LOG_DIR / "ui_http.log"
_UI_FILE_SINK_ID: int | None = None


def _configure_ui_file_logging() -> None:
    """Build internal configure ui file logging.

    Returns:
        None: None.
    """

    global _UI_FILE_SINK_ID
    if _UI_FILE_SINK_ID is not None:
        return

    UI_LOG_DIR.mkdir(parents=True, exist_ok=True)
    _UI_FILE_SINK_ID = logger.add(
        str(UI_HTTP_LOG_FILE),
        level="INFO",
        rotation="10 MB",
        retention="14 days",
        encoding="utf-8",
        enqueue=True,
        filter=lambda record: "[ui." in record["message"],
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}",
    )
    logger.info(
        "[ui.logging] file sink enabled path={}", str(UI_HTTP_LOG_FILE.resolve())
    )


def _should_log_request(path: str) -> bool:
    """Build internal should log request.

    Args:
        path (str): Filesystem path for the operation.

    Returns:
        bool: True if should log request, otherwise False.
    """

    return path == "/api/health" or path.startswith("/api/ui/")


def _sanitize_log_payload(value: Any) -> Any:
    """Build internal sanitize log payload.

    Args:
        value (Any): The value value.

    Returns:
        Any: The result produced by the operation.
    """

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key == "data" and isinstance(item, str):
                sanitized[key] = f"<omitted base64 payload len={len(item)}>"
            elif key == "uploaded_files" and isinstance(item, list):
                sanitized[key] = [_sanitize_log_payload(entry) for entry in item]
            else:
                sanitized[key] = _sanitize_log_payload(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_log_payload(item) for item in value]
    return value


def _decode_request_body(body: bytes) -> Any:
    """Build internal decode request body.

    Args:
        body (bytes): The body value.

    Returns:
        Any: The result produced by the operation.
    """

    if not body:
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body.decode("utf-8", errors="replace")
    return _sanitize_log_payload(parsed)


app = FastAPI(
    title="SolidWorks Prefab UI Server",
    version="0.1.0",
    summary="FastAPI backend for the interactive SolidWorks Prefab dashboard.",
)

_configure_ui_file_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(127\.0\.0\.1|localhost):\d+$",
    allow_methods=["*"],
    allow_headers=["*"],
)


# TODO: Tasks pending completion -@andre at 4/15/2026, 7:57:32 PM
# Need to update on_event to the correct fastapi lifecycle event hook
@app.on_event("startup")
async def _startup_ingest_design_knowledge() -> None:
    """Auto-ingest bundled design knowledge markdown files into FAISS on first startup.

    Returns:
        None: None.
    """
    import logging as _logging

    _log = _logging.getLogger(__name__)
    knowledge_dir = FilePath(__file__).parent.parent / "agents" / "design_knowledge"
    if not knowledge_dir.is_dir():
        return
    md_files = sorted(knowledge_dir.glob("*.md"))
    if not md_files:
        return
    try:
        from ..agents.vector_rag import VectorRAGIndex  # noqa: PLC0415

        namespace = "solidworks-design-knowledge"
        rag_dir = FilePath(".solidworks_mcp") / "rag"
        idx = VectorRAGIndex.load(namespace=namespace, rag_dir=rag_dir)
        # Only re-ingest if the index is empty (fresh install) or stale
        if idx.chunk_count == 0:
            for md_file in md_files:
                text = md_file.read_text(encoding="utf-8")
                idx.ingest_text(
                    text, source=md_file.name, tags=[namespace, md_file.stem]
                )
            idx.save()
            _log.info(
                "Auto-ingested %d design knowledge files into FAISS namespace '%s'",
                len(md_files),
                namespace,
            )
        else:
            _log.debug(
                "FAISS namespace '%s' already loaded (%d chunks) — skipping auto-ingest",
                namespace,
                idx.chunk_count,
            )
    except ImportError:
        _log.debug(
            "faiss/sentence-transformers not installed — skipping design knowledge auto-ingest"
        )
    except Exception as exc:
        _log.warning("Design knowledge auto-ingest failed (non-fatal): %s", exc)


@app.middleware("http")
async def log_ui_requests(request: Request, call_next):
    """Handle log ui requests.

    Args:
        request (Request): The request value.
        call_next (Any): The call next value.

    Returns:
        Any: The result produced by the operation.
    """

    if not _should_log_request(request.url.path):
        return await call_next(request)

    started_at = time.perf_counter()
    raw_body = await request.body()
    payload = {
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params),
        "body": _decode_request_body(raw_body),
    }

    logger.info(
        "[ui.http.request] payload={}",
        json.dumps(payload, ensure_ascii=True, default=str),
    )

    async def receive() -> dict[str, Any]:
        """Handle receive.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
        """

        return {"type": "http.request", "body": raw_body, "more_body": False}

    request = Request(request.scope, receive)

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.exception(
            "[ui.http.error] method={} path={} duration_ms={} error={}",
            request.method,
            request.url.path,
            duration_ms,
            exc,
        )
        raise

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "[ui.http.response] method={} path={} status_code={} duration_ms={}",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


app.mount(
    "/previews",
    StaticFiles(directory=str(ensure_preview_dir().resolve())),
    name="previews",
)

# ---------------------------------------------------------------------------
# Include modular routers
# ---------------------------------------------------------------------------
app.include_router(session_router.router)
app.include_router(model_router.router)
app.include_router(preview_router.router)
app.include_router(llm_router.router)
app.include_router(checkpoint_router.router)
app.include_router(docs_router.router)
app.include_router(local_model_router.router)
app.include_router(viewer_router.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


def main() -> None:
    """Run the dashboard backend locally."""
    uvicorn.run(app, host="127.0.0.1", port=8766)


if __name__ == "__main__":
    main()
