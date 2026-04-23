"""
FastAPI backend for the Prefab CAD assistant dashboard.

REST API endpoints for dashboard actions:
- GET /api/ui/state - Hydrate UI with current session state
- POST /api/ui/brief/approve - Accept user goal
- POST /api/ui/clarify - Call GitHub Copilot to generate Q&A
- POST /api/ui/family/inspect - Call GitHub Copilot to classify design family
- POST /api/ui/family/accept - Accept proposed family
- POST /api/ui/checkpoints/execute-next - Execute next checkpoint (adapter-backed; unsupported tools marked MOCKED)
- POST /api/ui/preview/refresh - Sync 3D view from SolidWorks export_image
- POST /api/ui/manual-sync/reconcile - Detect manual edits via snapshot diff
- GET /previews/* - Serve static PNG preview images
- GET /docs - FastAPI OpenAPI UI for local endpoint inspection

LLM Integration:
- Clarify button: GitHub Copilot (default: github:openai/gpt-4.1)
- Inspect button: GitHub Copilot family classification
- Requires: GH_TOKEN or GITHUB_API_KEY environment variable with models:read scope
"""

from __future__ import annotations

import json
import time
from pathlib import Path as FilePath
from typing import Any

import uvicorn
from fastapi import FastAPI, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, field_validator

from .local_llm import (
    LocalAgentResult,
    LocalModelProbeResult,
    LocalModelPullRequest,
    LocalModelPullResult,
    LocalModelQueryRequest,
)
from .service import (
    DEFAULT_API_ORIGIN,
    DEFAULT_SESSION_ID,
    DEFAULT_USER_GOAL,
    accept_family_choice,
    approve_design_brief,
    build_dashboard_state,
    build_dashboard_trace_payload,
    connect_target_model,
    ensure_preview_dir,
    execute_next_checkpoint,
    highlight_feature,
    ingest_reference_source,
    fetch_docs_context,
    load_session_context,
    inspect_family,
    run_go_orchestration,
    reconcile_manual_edits,
    refresh_preview,
    request_clarifications,
    save_session_context,
    select_workflow_mode,
    open_target_model,
    update_session_notes,
    update_ui_preferences,
)

UI_LOG_DIR = FilePath(".solidworks_mcp") / "ui_logs"
UI_HTTP_LOG_FILE = UI_LOG_DIR / "ui_http.log"
_UI_FILE_SINK_ID: int | None = None


def _configure_ui_file_logging() -> None:
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
    return path == "/api/health" or path.startswith("/api/ui/")


def _sanitize_log_payload(value: Any) -> Any:
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
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body.decode("utf-8", errors="replace")
    return _sanitize_log_payload(parsed)


class SessionRequest(BaseModel):
    """Base request payload containing session scope."""

    session_id: str = DEFAULT_SESSION_ID


class GoalRequest(SessionRequest):
    """Request payload for endpoints that operate on the current design goal."""

    user_goal: str = DEFAULT_USER_GOAL


class ClarifyWithAnswerRequest(GoalRequest):
    """Request payload for clarify that includes the user's typed answers."""

    user_answer: str = ""


class FamilyAcceptRequest(SessionRequest):
    """Request payload for family acceptance."""

    family: str | None = None


class PreviewRefreshRequest(SessionRequest):
    """Request payload for preview refresh requests."""

    orientation: str = "current"


class FeatureSelectRequest(SessionRequest):
    """Request payload for highlighting a named feature in the SolidWorks model tree."""

    feature_name: str


class PreferencesUpdateRequest(SessionRequest):
    """Request payload for assumptions and model preference updates."""

    assumptions_text: str
    model_provider: str = "github"
    model_profile: str = "balanced"
    model_name: str | None = None
    local_endpoint: str | None = None


class WorkflowSelectionRequest(SessionRequest):
    """Request payload for selecting the onboarding workflow branch."""

    workflow_mode: str


class UploadedFilePayload(BaseModel):
    """Browser-uploaded file payload returned by Prefab's OpenFilePicker action."""

    name: str
    size: int
    type: str
    data: str


class ConnectTargetModelRequest(SessionRequest):
    """Request payload for attaching an active SolidWorks target model."""

    model_path: str | None = None
    uploaded_files: list[UploadedFilePayload] | None = None
    feature_target_text: str | None = None

    @field_validator("uploaded_files", mode="before")
    @classmethod
    def _coerce_empty_uploaded_files(cls, v: object) -> object:
        """Coerce empty string or empty list to None so Pydantic accepts it."""
        if v == "" or v == []:
            return None
        return v


class RagIngestRequest(SessionRequest):
    """Request payload for BYO retrieval ingestion from a local path or URL."""

    source_path: str
    namespace: str = "engineering-reference"
    chunk_size: int = 1200
    overlap: int = 200


class GoOrchestrationRequest(SessionRequest):
    """Request payload for global Go orchestration action."""

    user_goal: str = DEFAULT_USER_GOAL
    assumptions_text: str | None = None
    user_answer: str = ""


class DocsContextRequest(SessionRequest):
    """Request payload for docs-context refresh."""

    query: str = "SolidWorks MCP endpoints"


class NotesUpdateRequest(SessionRequest):
    """Request payload for saving free-form engineering notes."""

    notes_text: str = ""


class ContextSaveRequest(SessionRequest):
    """Request payload for saving context to plain JSON snapshot."""

    context_name: str | None = None


class ContextLoadRequest(SessionRequest):
    """Request payload for loading context snapshot from plain JSON."""

    context_file: str | None = None


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
    """Auto-ingest bundled design knowledge markdown files into FAISS on first startup."""
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


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/ui/state")
async def get_state(session_id: str = Query(DEFAULT_SESSION_ID)) -> dict[str, Any]:
    """Hydrate UI state from active session database."""
    return build_dashboard_state(session_id, api_origin=DEFAULT_API_ORIGIN)


@app.get("/api/ui/debug/session")
async def get_debug_session(
    session_id: str = Query(DEFAULT_SESSION_ID),
) -> dict[str, Any]:
    """Return a verbose debug snapshot for the active UI session."""
    return build_dashboard_trace_payload(
        session_id,
        api_origin=DEFAULT_API_ORIGIN,
    )


@app.post("/api/ui/brief/approve")
async def approve_brief(payload: GoalRequest) -> dict[str, Any]:
    """Accept the user-provided design goal."""
    return approve_design_brief(payload.session_id, payload.user_goal)


@app.post("/api/ui/preferences/update")
async def update_preferences(payload: PreferencesUpdateRequest) -> dict[str, Any]:
    """Persist assumptions and provider/model preferences in session metadata."""
    return update_ui_preferences(
        payload.session_id,
        assumptions_text=payload.assumptions_text,
        model_provider=payload.model_provider,
        model_profile=payload.model_profile,
        model_name=payload.model_name,
        local_endpoint=payload.local_endpoint,
    )


@app.post("/api/ui/workflow/select")
async def update_workflow_mode(payload: WorkflowSelectionRequest) -> dict[str, Any]:
    """Persist the workflow choice shown on the opening dashboard screen."""
    return select_workflow_mode(
        payload.session_id,
        workflow_mode=payload.workflow_mode,
    )


@app.post("/api/ui/model/connect")
async def connect_model(payload: ConnectTargetModelRequest) -> dict[str, Any]:
    """Attach a target SolidWorks document and derive grounded feature-tree context."""
    return await connect_target_model(
        payload.session_id,
        model_path=payload.model_path,
        uploaded_files=(
            [uploaded.model_dump() for uploaded in payload.uploaded_files]
            if payload.uploaded_files
            else None
        ),
        feature_target_text=payload.feature_target_text,
        api_origin=DEFAULT_API_ORIGIN,
    )


@app.post("/api/ui/model/open")
async def open_model(payload: ConnectTargetModelRequest) -> dict[str, Any]:
    """Open a target SolidWorks document first, before full connect/preview processing."""
    return await open_target_model(
        payload.session_id,
        model_path=payload.model_path,
        uploaded_files=(
            [uploaded.model_dump() for uploaded in payload.uploaded_files]
            if payload.uploaded_files
            else None
        ),
        feature_target_text=payload.feature_target_text,
        api_origin=DEFAULT_API_ORIGIN,
    )


@app.post("/api/ui/rag/ingest")
async def ingest_rag_source(payload: RagIngestRequest) -> dict[str, Any]:
    """Ingest a user-provided PDF/text source into a local retrieval index."""
    return ingest_reference_source(
        payload.session_id,
        source_path=payload.source_path,
        namespace=payload.namespace,
        chunk_size=payload.chunk_size,
        overlap=payload.overlap,
    )


@app.post("/api/ui/orchestrate/go")
async def orchestrate_go(payload: GoOrchestrationRequest) -> dict[str, Any]:
    """Run one end-to-end update across workflow, review, and model output lanes."""
    return await run_go_orchestration(
        payload.session_id,
        user_goal=payload.user_goal,
        assumptions_text=payload.assumptions_text,
        user_answer=payload.user_answer,
        api_origin=DEFAULT_API_ORIGIN,
    )


@app.post("/api/ui/docs/context")
async def refresh_docs_context(payload: DocsContextRequest) -> dict[str, Any]:
    """Fetch a docs excerpt from the local docs endpoint using a query hint."""
    return fetch_docs_context(
        payload.session_id,
        docs_query=payload.query,
        api_origin=DEFAULT_API_ORIGIN,
    )


@app.post("/api/ui/notes/update")
async def save_notes(payload: NotesUpdateRequest) -> dict[str, Any]:
    """Persist engineering notes for the current dashboard session."""
    return update_session_notes(
        payload.session_id,
        notes_text=payload.notes_text,
        api_origin=DEFAULT_API_ORIGIN,
    )


@app.post("/api/ui/context/save")
async def save_context(payload: ContextSaveRequest) -> dict[str, Any]:
    """Save current dashboard context to plain JSON and metadata."""
    return save_session_context(
        payload.session_id,
        context_name=payload.context_name,
        api_origin=DEFAULT_API_ORIGIN,
    )


@app.post("/api/ui/context/load")
async def load_context(payload: ContextLoadRequest) -> dict[str, Any]:
    """Load dashboard context from plain JSON snapshot."""
    return load_session_context(
        payload.session_id,
        context_file=payload.context_file,
        api_origin=DEFAULT_API_ORIGIN,
    )


@app.post("/api/ui/clarify")
async def clarify_goal(payload: ClarifyWithAnswerRequest) -> dict[str, Any]:
    """
    Call GitHub Copilot to normalize brief and generate clarifying questions.

    Requires GH_TOKEN or GITHUB_API_KEY with models:read scope.
    Accepts optional user_answer with the user's typed clarifications.
    """
    return await request_clarifications(
        payload.session_id, payload.user_goal, user_answer=payload.user_answer
    )


@app.post("/api/ui/family/inspect")
async def inspect_goal_family(payload: GoalRequest) -> dict[str, Any]:
    """
    Call GitHub Copilot to classify design family and suggest checkpoints.

    Returns: family (string), confidence (low/medium/high), evidence (list),
    warnings (list), checkpoints (with tools and rationale).
    """
    return await inspect_family(payload.session_id, payload.user_goal)


@app.post("/api/ui/family/accept")
async def accept_family(payload: FamilyAcceptRequest) -> dict[str, Any]:
    """Accept the proposed design family and advance status."""
    return accept_family_choice(payload.session_id, payload.family)


@app.post("/api/ui/checkpoints/execute-next")
async def execute_checkpoint(payload: SessionRequest) -> dict[str, Any]:
    """
    Execute the next pending checkpoint.

    Runs supported adapter tools (create_sketch, add_line, create_extrusion, create_cut).
    Unsupported tools are marked as MOCKED in checkpoint results and UI state.
    """
    return await execute_next_checkpoint(payload.session_id)


@app.post("/api/ui/preview/refresh")
async def refresh_preview_image(payload: PreviewRefreshRequest) -> dict[str, Any]:
    """
    Refresh the 3D view pane by exporting the current SolidWorks viewport.

    Supported orientations: "front", "top", "right", "isometric", "current".
    Uses export_image() from the active adapter (requires SolidWorks COM available).
    """
    return await refresh_preview(
        payload.session_id,
        orientation=payload.orientation,
        api_origin=DEFAULT_API_ORIGIN,
    )


@app.post("/api/ui/feature/select")
async def select_feature_endpoint(payload: FeatureSelectRequest) -> dict[str, Any]:
    """
    Select and highlight a named feature in the active SolidWorks model.

    Uses SelectByID2 to locate the feature by name, trying common entity type
    strings (BODYFEATURE, SKETCH, PLANE, COMPONENT) in priority order.
    Returns the full dashboard state with ``selected_feature_name`` updated.
    """
    return await highlight_feature(
        payload.session_id,
        payload.feature_name,
        api_origin=DEFAULT_API_ORIGIN,
    )


@app.post("/api/ui/manual-sync/reconcile")
async def reconcile_edits(payload: SessionRequest) -> dict[str, Any]:
    return reconcile_manual_edits(payload.session_id)


@app.get("/api/ui/local-model/probe")
async def probe_local_model_endpoint() -> LocalModelProbeResult:
    """
    Probe for a running Ollama server and recommend the best Gemma model tier.

    Returns a typed ``LocalModelProbeResult`` with hardware detection results,
    availability, pull status, and the ``service_model`` string suitable for
    passing as ``model_name`` to clarify/inspect actions.
    """
    from .local_llm import probe_local_model  # noqa: PLC0415

    return await probe_local_model()


@app.post("/api/ui/local-model/pull")
async def pull_local_model_endpoint(
    payload: LocalModelPullRequest,
) -> LocalModelPullResult:
    """
    Trigger an Ollama pull for the specified model name (e.g. ``gemma3:12b``).

    The pull runs synchronously via Ollama's ``/api/pull`` endpoint.
    Large models (27B) may take several minutes to download.
    """
    from .local_llm import pull_ollama_model  # noqa: PLC0415

    return await pull_ollama_model(model=payload.model, endpoint=payload.endpoint)


@app.post("/api/ui/local-model/query")
async def query_local_model_endpoint(
    payload: LocalModelQueryRequest,
) -> LocalAgentResult:
    """
    Run a free-form prompt against the local Ollama model.

    The request body carries a ``prompt`` and optional ``system_prompt``.
    The LLM response is validated by pydantic-ai and returned as a typed
    ``LocalAgentResult`` with ``success``, ``data`` (plain string), and
    ``config`` echoing the connection settings used.
    """
    from pydantic import BaseModel as _BaseModel

    from .local_llm import LocalLLMConfig, run_local_agent  # noqa: PLC0415

    class _FreeFormResponse(_BaseModel):
        text: str

    config = LocalLLMConfig.from_env()
    if payload.endpoint:
        config = config.model_copy(
            update={
                "endpoint": payload.endpoint,
                "openai_endpoint": f"{payload.endpoint}/v1",
            }
        )
    if payload.model:
        service_model = (
            payload.model
            if payload.model.startswith("local:")
            else f"local:{payload.model}"
        )
        config = config.model_copy(update={"service_model": service_model})

    return await run_local_agent(
        system_prompt=payload.system_prompt,
        user_prompt=payload.prompt,
        result_type=_FreeFormResponse,
        config=config,
    )


_VIEWER_HTML = """\
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>3D Model Viewer</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0f172a; color: #94a3b8; font-family: system-ui, sans-serif; overflow: hidden; }
#wrap { width: 100vw; height: 100vh; }
#overlay { position: fixed; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 10px; pointer-events: none; }
#status { font-size: 13px; text-align: center; max-width: 300px; line-height: 1.6; }
#hint { position: fixed; bottom: 10px; left: 50%; transform: translateX(-50%);
    font-size: 11px; opacity: 0.35; user-select: none; }
#fmt-badge { position: fixed; top: 8px; right: 10px; font-size: 10px;
    opacity: 0.4; letter-spacing: 0.05em; user-select: none; }
</style></head><body>
<div id="wrap"></div>
<div id="overlay">
    <div id="icon" style="font-size:28px">&#9203;</div>
    <div id="status">Loading 3D model&#8230;</div>
</div>
<div id="hint">Drag to rotate &middot; Scroll to zoom &middot; Right-drag to pan</div>
<div id="fmt-badge"></div>
<script type="importmap">{"imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.165.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.165.0/examples/jsm/"
}}</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

const params = new URLSearchParams(location.search);
const pathParts = location.pathname.split('/').filter(Boolean);
const pathSessionId = pathParts[pathParts.length - 1] || 'prefab-dashboard';
const sessionId = params.get('session_id') || pathSessionId;
const ts = params.get('t') || '0';
const fmt = params.get('fmt') || 'stl';   // 'glb' | 'stl' | 'none'

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setSize(window.innerWidth, window.innerHeight);
document.getElementById('wrap').appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0f172a);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.01, 100000);
camera.position.set(0, 100, 250);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;

scene.add(new THREE.AmbientLight(0xffffff, 0.8));
const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
dirLight.position.set(1, 2, 1.5);
scene.add(dirLight);
const fillLight = new THREE.DirectionalLight(0x8ab4f8, 0.4);
fillLight.position.set(-1, -1, -1);
scene.add(fillLight);

// Fallback material used only for STL (no material data in file)
const stlMaterial = new THREE.MeshPhongMaterial({
    color: 0x3b82f6, specular: 0x1e3a5f, shininess: 60, side: THREE.DoubleSide
});

function fitCamera(object) {
    const box = new THREE.Box3().setFromObject(object);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z) || 100;
    camera.position.set(center.x, center.y + maxDim * 0.6, center.z + maxDim * 2);
    camera.near = maxDim * 0.001;
    camera.far = maxDim * 200;
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
}

function hideOverlay() {
    document.getElementById('overlay').style.display = 'none';
}

function showError(msg) {
    document.getElementById('icon').textContent = '( )';
    document.getElementById('status').textContent = msg;
}

function onProgress(p) {
    const pct = p.total ? Math.round(p.loaded / p.total * 100) : 0;
    document.getElementById('status').textContent = 'Loading\\u2026 ' + pct + '%';
}

if (fmt === 'glb') {
    document.getElementById('fmt-badge').textContent = 'GLB';
    const glbUrl = location.origin + '/previews/' + sessionId + '.glb?_t=' + ts;
    new GLTFLoader().load(
        glbUrl,
        (gltf) => {
            hideOverlay();
            const model = gltf.scene;
            // Ensure all meshes render double-sided so thin faces don't disappear
            model.traverse((node) => {
                if (node.isMesh && node.material) {
                    const mats = Array.isArray(node.material) ? node.material : [node.material];
                    mats.forEach((m) => { m.side = THREE.DoubleSide; });
                }
            });
            scene.add(model);
            fitCamera(model);
        },
        onProgress,
        () => showError('No 3D model file yet. Attach a SolidWorks model, then click Refresh 3D View.')
    );
} else if (fmt === 'stl') {
    document.getElementById('fmt-badge').textContent = 'STL';
    const stlUrl = location.origin + '/previews/' + sessionId + '.stl?_t=' + ts;
    new STLLoader().load(
        stlUrl,
        (geometry) => {
            hideOverlay();
            geometry.computeBoundingBox();
            geometry.center();
            geometry.computeVertexNormals();
            const mesh = new THREE.Mesh(geometry, stlMaterial);
            scene.add(mesh);
            fitCamera(mesh);
        },
        onProgress,
        () => showError('No 3D model file yet. Attach a SolidWorks model, then click Refresh 3D View.')
    );
} else {
    showError('No 3D model file yet. Attach a SolidWorks model, then click Refresh 3D View.');
}

window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});

(function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
})();
</script></body></html>
"""


@app.get("/api/ui/viewer/{session_id}", response_class=HTMLResponse)
async def get_viewer(
    session_id: str = Path(description="Session identifier for STL file routing"),
) -> HTMLResponse:
    """Serve the embedded Three.js 3D model viewer page."""
    return HTMLResponse(content=_VIEWER_HTML, media_type="text/html")


def main() -> None:
    """Run the dashboard backend locally."""
    uvicorn.run(app, host="127.0.0.1", port=8766)


if __name__ == "__main__":
    main()
