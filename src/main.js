/**
 * GeoSplat — 3D Geospatial Gaussian Splatting Viewer
 * Built on THREE.js + @sparkjsdev/spark
 */

import * as THREE from 'three';
import { SplatMesh } from '@sparkjsdev/spark';

// ── State ──────────────────────────────────────────
let scene, camera, renderer, splatMesh;
let animationId;
let keys = {};

// ── DOM refs ───────────────────────────────────────
const container = document.getElementById('canvas-container');
const statusEl = document.getElementById('status');
const dropOverlay = document.getElementById('drop-overlay');
const mapContainer = document.getElementById('map-container');

// ── Initialize THREE.js Scene ──────────────────────
function initScene() {
  renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1a1a2e);

  camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 5000);
  camera.position.set(5, 3, 10);
  camera.lookAt(0, 0, 0);

  // Grid & axes for reference
  const grid = new THREE.GridHelper(20, 20, 0x444466, 0x222244);
  scene.add(grid);
  scene.add(new THREE.AxesHelper(3));

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });
}

// ── Load .splat from ArrayBuffer ───────────────────
async function loadSplatBuffer(buffer, fileName) {
  statusEl.textContent = 'Loading...';
  try {
    if (splatMesh) {
      scene.remove(splatMesh);
      splatMesh.dispose();
      splatMesh = null;
    }

    splatMesh = new SplatMesh({
      fileBytes: buffer,
      fileName,
      onProgress: (e) => {
        if (e.total) {
          statusEl.textContent = `Loading... ${((e.loaded / e.total) * 100).toFixed(0)}%`;
        }
      },
      onLoad: (mesh) => {
        const n = mesh.getNumSplats?.() ?? '?';
        statusEl.textContent = `Loaded: ${n.toLocaleString()} gaussians`;
        fitCamera();
      },
    });

    // Wait for async init
    await splatMesh.initialized;
    scene.add(splatMesh);

    const count = splatMesh.getNumSplats();
    statusEl.textContent = `Loaded: ${count.toLocaleString()} gaussians`;
    fitCamera();

  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
    console.error('Load error:', err);
  }
}

// ── Fit camera to scene ────────────────────────────
function fitCamera() {
  if (!splatMesh) return;
  try {
    const box = splatMesh.getBoundingBox();
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    camera.position.copy(center);
    camera.position.z += maxDim * 1.5;
    camera.position.y += maxDim * 0.3;
    camera.lookAt(center);
  } catch (e) {
    // getBoundingBox might fail if not yet initialized
  }
}

// ── Render loop ────────────────────────────────────
function animate() {
  animationId = requestAnimationFrame(animate);

  // WASD + QE fly controls
  const speed = 0.5;
  const fwd = new THREE.Vector3();
  camera.getWorldDirection(fwd);
  const right = new THREE.Vector3();
  right.crossVectors(fwd, camera.up).normalize();

  if (keys['w']) camera.position.addScaledVector(fwd, speed);
  if (keys['s']) camera.position.addScaledVector(fwd, -speed);
  if (keys['a']) camera.position.addScaledVector(right, -speed);
  if (keys['d']) camera.position.addScaledVector(right, speed);
  if (keys['q']) camera.position.y -= speed;
  if (keys['e']) camera.position.y += speed;

  renderer.render(scene, camera);
}

// ── Drag-and-drop ──────────────────────────────────
document.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropOverlay.classList.add('active');
});

document.addEventListener('dragleave', (e) => {
  if (e.target === dropOverlay) dropOverlay.classList.remove('active');
});

document.addEventListener('drop', async (e) => {
  e.preventDefault();
  dropOverlay.classList.remove('active');
  const file = e.dataTransfer.files?.[0];
  if (!file) return;
  const buf = await file.arrayBuffer();
  await loadSplatBuffer(buf, file.name);
});

// ── UI Handlers ────────────────────────────────────
document.getElementById('btn-open').addEventListener('click', () => {
  const inp = document.createElement('input');
  inp.type = 'file';
  inp.accept = '.splat,.ply,.spz';
  inp.onchange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const buf = await file.arrayBuffer();
    await loadSplatBuffer(buf, file.name);
  };
  inp.click();
});

document.getElementById('btn-map').addEventListener('click', () => {
  mapContainer.classList.toggle('visible');
  document.getElementById('btn-map').classList.toggle(
    'active',
    mapContainer.classList.contains('visible')
  );
});

document.getElementById('btn-reset').addEventListener('click', fitCamera);

// ── Keyboard ───────────────────────────────────────
document.addEventListener('keydown', (e) => {
  keys[e.key.toLowerCase()] = true;
  if (e.key === '?' || e.key === 'h') {
    const help = document.getElementById('help');
    help.style.display = help.style.display === 'none' ? '' : 'none';
  }
});
document.addEventListener('keyup', (e) => { keys[e.key.toLowerCase()] = false; });

// ── Mouse orbit ────────────────────────────────────
let dragging = false, prev = { x: 0, y: 0 };

container.addEventListener('mousedown', (e) => {
  if (e.button === 0) { dragging = true; prev = { x: e.clientX, y: e.clientY }; }
});
window.addEventListener('mouseup', () => { dragging = false; });
window.addEventListener('mousemove', (e) => {
  if (!dragging) return;
  const dx = e.clientX - prev.x;
  const dy = e.clientY - prev.y;
  prev = { x: e.clientX, y: e.clientY };

  const sens = 0.003;
  const euler = new THREE.Euler(0, 0, 0, 'YXZ');
  euler.setFromQuaternion(camera.quaternion);
  euler.y -= dx * sens;
  euler.x -= dy * sens;
  euler.x = Math.max(-Math.PI / 2 + 0.01, Math.min(Math.PI / 2 - 0.01, euler.x));
  camera.quaternion.setFromEuler(euler);
});

container.addEventListener('wheel', (e) => {
  e.preventDefault();
  const fwd = new THREE.Vector3();
  camera.getWorldDirection(fwd);
  camera.position.addScaledVector(fwd, e.deltaY * 0.1);
}, { passive: false });

// ── Start ──────────────────────────────────────────
initScene();
animate();

console.log('🚁 GeoSplat ready — drop a .splat file to view');

// Load sample if URL param provided
const p = new URLSearchParams(location.search);
const url = p.get('url');
if (url) {
  fetch(url).then(r => r.arrayBuffer()).then(b => loadSplatBuffer(b, url));
}
