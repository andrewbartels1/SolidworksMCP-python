"""Three.js 3D model viewer route for the Prefab CAD dashboard.

# TODO: move _VIEWER_HTML to a Jinja2 template file at templates/viewer.html
"""

from __future__ import annotations

from fastapi import APIRouter, Path
from fastapi.responses import HTMLResponse

router = APIRouter()

# ---------------------------------------------------------------------------
# Embedded Three.js viewer HTML
# ---------------------------------------------------------------------------
# TODO: move to templates/viewer.html and serve via Jinja2TemplateResponse
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
const fmt = params.get('fmt') || 'stl';

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

function hideOverlay() { document.getElementById('overlay').style.display = 'none'; }
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
    new GLTFLoader().load(glbUrl, (gltf) => {
        hideOverlay();
        const model = gltf.scene;
        model.traverse((node) => {
            if (node.isMesh && node.material) {
                const mats = Array.isArray(node.material) ? node.material : [node.material];
                mats.forEach((m) => { m.side = THREE.DoubleSide; });
            }
        });
        scene.add(model);
        fitCamera(model);
    }, onProgress, () => showError('No 3D model file yet. Attach a SolidWorks model, then click Refresh 3D View.'));
} else if (fmt === 'stl') {
    document.getElementById('fmt-badge').textContent = 'STL';
    const stlUrl = location.origin + '/previews/' + sessionId + '.stl?_t=' + ts;
    new STLLoader().load(stlUrl, (geometry) => {
        hideOverlay();
        geometry.computeBoundingBox();
        geometry.center();
        geometry.computeVertexNormals();
        const mesh = new THREE.Mesh(geometry, stlMaterial);
        scene.add(mesh);
        fitCamera(mesh);
    }, onProgress, () => showError('No 3D model file yet. Attach a SolidWorks model, then click Refresh 3D View.'));
} else {
    showError('No 3D model file yet. Attach a SolidWorks model, then click Refresh 3D View.');
}

window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});
(function animate() { requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); })();
</script></body></html>
"""


@router.get("/api/ui/viewer/{session_id}", response_class=HTMLResponse)
async def get_viewer(
    session_id: str = Path(description="Session identifier for 3D model file routing"),
) -> HTMLResponse:
    """Serve the embedded Three.js 3D model viewer page."""
    return HTMLResponse(content=_VIEWER_HTML, media_type="text/html")
