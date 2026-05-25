# 🚁 GeoSplat

**Web-based 3D Geospatial Gaussian Splatting viewer** — drop your `.splat` file and fly through a photorealistic 3D scene reconstructed from drone photos.

Built on [THREE.js](https://threejs.org/) + [Spark](https://github.com/sparkjsdev/spark) — the most advanced open-source 3DGS renderer for the web.

## Quick Start

```bash
npm install
npm run dev        # opens http://localhost:3000
```

Then drag a `.splat` or `.ply` file onto the page.

## Controls

| Input | Action |
|-------|--------|
| 🖱 Left-drag | Orbit |
| 🖱 Right-drag / Shift+drag | Pan |
| Scroll / Pinch | Zoom in/out |
| `W A S D` | Fly (FPS mode) |
| `Q` / `E` | Down / Up |
| `?` | Toggle help |

## Pipeline: Drone Photos → 3D Viewer

### Step 1: Preprocess with COLMAP

```bash
# Install COLMAP (macOS)
brew install colmap

# Run preprocessing
python pipeline/colmap_preprocess.py /path/to/drone_photos/ -o ./output --extract-gps
```

This extracts SIFT features, runs Structure-from-Motion, and exports camera poses.

### Step 2: Train 3D Gaussian Splatting

```bash
# Using nerfstudio + gsplat
pip install nerfstudio gsplat
ns-train gaussian-splatting --data ./output/gsplat_input/
```

### Step 3: Convert to .splat

```bash
# Convert the trained PLY to compact .splat format
python pipeline/convert.py exports/point_cloud.ply -o scene.splat --georef 30.25,120.12,50
```

### Step 4: View

Drop `scene.splat` onto the GeoSplat viewer, or serve it:

```bash
npm run build     # produces dist/
# Deploy dist/ to any static host (GitHub Pages, S3, etc.)
```

## File Format

`.splat` — 32 bytes per Gaussian:

| Field | Bytes | Type |
|-------|-------|------|
| Position (x,y,z) | 12 | float32 × 3 |
| Scale (x,y,z) | 12 | float32 × 3 |
| Color (RGBA) | 4 | uint8 × 4 |
| Rotation (quaternion) | 4 | uint8 × 4 |

1 million Gaussians ≈ 32 MB — streams efficiently over the web.

## Tech Stack

- **Renderer**: [@sparkjsdev/spark](https://github.com/sparkjsdev/spark) v2 (THREE.js WebGL renderer)
- **3D Engine**: THREE.js
- **Training**: [gsplat](https://github.com/nerfstudio-project/gsplat) + nerfstudio
- **SfM**: COLMAP (or DUSt3R for better drone results)
- **Build**: Vite

## Roadmap

- [x] .splat file viewer with orbit/fly controls
- [x] Drag-and-drop file loading
- [x] Python PLY→.splat conversion pipeline
- [x] COLMAP preprocessing script
- [ ] MapLibre GL JS integration (2D map context)
- [ ] Measurement tools (distance, area)
- [ ] Tiling / LOD for large scenes (>5M gaussians)
- [ ] Annotation system
- [ ] Camera bookmark presets

## Acknowledgments

- INRIA's [3D Gaussian Splatting](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/)
- [antimatter15/splat](https://github.com/antimatter15/splat) — pioneering WebGL viewer
- [Spark](https://sparkjs.dev/) — THREE.js 3DGS renderer
- [DroneSplat](https://github.com/BITyia/DroneSplat) — CVPR 2025 drone-specific pipeline

## License

MIT
