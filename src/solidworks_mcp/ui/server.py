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

from typing import Any

import uvicorn
from fastapi import FastAPI, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .service import (
    DEFAULT_API_ORIGIN,
    DEFAULT_SESSION_ID,
    DEFAULT_USER_GOAL,
    accept_family_choice,
    approve_design_brief,
    build_dashboard_state,
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


class RagIngestRequest(SessionRequest):
    """Request payload for BYO retrieval ingestion from a local path or URL."""

    source_path: str
    namespace: str = "engineering-reference"
    chunk_size: int = 1200
    overlap: int = 200


app = FastAPI(
    title="SolidWorks Prefab UI Server",
    version="0.1.0",
    summary="FastAPI backend for the interactive SolidWorks Prefab dashboard.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5175",
        "http://localhost:5175",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.post("/api/ui/manual-sync/reconcile")
async def reconcile_edits(payload: SessionRequest) -> dict[str, Any]:
    """
    Detect manual edits by comparing latest two snapshots.

    MOCKED: Simple fingerprint comparison. Future: capture model state
    (features, masses, sketches) and provide richer diff.
    """
    return reconcile_manual_edits(payload.session_id)


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
</style></head><body>
<div id="wrap"></div>
<div id="overlay">
    <div id="icon" style="font-size:28px">&#9203;</div>
    <div id="status">Loading 3D model&#8230;</div>
</div>
<div id="hint">Drag to rotate &middot; Scroll to zoom &middot; Right-drag to pan</div>
<script type="importmap">{"imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.165.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.165.0/examples/jsm/"
}}</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

const params = new URLSearchParams(location.search);
const pathParts = location.pathname.split('/').filter(Boolean);
const pathSessionId = pathParts[pathParts.length - 1] || 'prefab-dashboard';
const sessionId = params.get('session_id') || pathSessionId;
const ts = params.get('t') || '0';
const stlUrl = location.origin + '/previews/' + sessionId + '.stl?_t=' + ts;

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
document.getElementById('wrap').appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0f172a);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.01, 100000);
camera.position.set(0, 100, 250);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;

scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
dirLight.position.set(1, 2, 1.5);
scene.add(dirLight);
const fillLight = new THREE.DirectionalLight(0x8ab4f8, 0.4);
fillLight.position.set(-1, -1, -1);
scene.add(fillLight);

const material = new THREE.MeshPhongMaterial({
    color: 0x3b82f6, specular: 0x1e3a5f, shininess: 60, side: THREE.DoubleSide
});

new STLLoader().load(
    stlUrl,
    (geometry) => {
        document.getElementById('overlay').style.display = 'none';
        geometry.computeBoundingBox();
        geometry.center();
        geometry.computeVertexNormals();
        const mesh = new THREE.Mesh(geometry, material);
        scene.add(mesh);
        const size = new THREE.Box3().setFromObject(mesh).getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z) || 100;
        camera.position.set(0, maxDim * 0.6, maxDim * 2);
        camera.near = maxDim * 0.001;
        camera.far = maxDim * 200;
        camera.updateProjectionMatrix();
        controls.update();
    },
    (progress) => {
        const pct = progress.total ? Math.round(progress.loaded / progress.total * 100) : 0;
        document.getElementById('status').textContent = 'Loading... ' + pct + '%';
    },
    () => {
        document.getElementById('icon').textContent = '( )';
        document.getElementById('status').textContent =
            'No 3D model file yet. Attach a SolidWorks model, then click Refresh 3D View.';
    }
);

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
