#!/usr/bin/env python3
"""
COLMAP → 3DGS Preprocessing Pipeline

Automates the standard drone-photo → gaussian splatting workflow:
  1. Extract frames / preprocess photos
  2. Run COLMAP (SfM) to get camera poses
  3. Convert to 3DGS/gsplat training format

Requirements:
  - COLMAP installed (brew install colmap or apt-get install colmap)
  - For GPS geotag support: pip install pillow exifread

Usage:
  python colmap_preprocess.py /path/to/drone_photos/ -o ./output
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run(cmd, desc=""):
    """Run a command, printing output as it goes."""
    print(f"\n  [{desc}] $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[-500:]}")
        raise RuntimeError(f"Command failed: {desc}")
    return result.stdout


def check_colmap():
    """Verify COLMAP is installed."""
    try:
        subprocess.run(["colmap", "help"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def preprocess(input_dir: Path, output_dir: Path):
    """
    Run COLMAP automatic reconstruction pipeline.

    Creates:
      output_dir/
        database.db         — COLMAP DB
        sparse/             — SfM output (cameras, images, points3D)
        undistorted/        — Undistorted images
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "database.db"
    image_dir = input_dir.resolve()
    sparse_dir = output_dir / "sparse"
    dense_dir = output_dir / "dense"

    # Step 1: Feature extraction
    print("\n=== Step 1: Feature Extraction ===")
    run([
        "colmap", "feature_extractor",
        "--database_path", str(db_path),
        "--image_path", str(image_dir),
        "--SiftExtraction.use_gpu", "1",
        "--SiftExtraction.max_image_size", "2000",
    ], "Extracting SIFT features")

    # Step 2: Feature matching
    print("\n=== Step 2: Feature Matching ===")
    run([
        "colmap", "exhaustive_matcher",
        "--database_path", str(db_path),
        "--SiftMatching.use_gpu", "1",
    ], "Exhaustive feature matching")

    # Step 3: Sparse reconstruction (SfM)
    print("\n=== Step 3: Sparse Reconstruction ===")
    sparse_dir.mkdir(exist_ok=True)
    run([
        "colmap", "mapper",
        "--database_path", str(db_path),
        "--image_path", str(image_dir),
        "--output_path", str(sparse_dir),
    ], "Sparse mapping (SfM)")

    # Step 4: Undistort images
    print("\n=== Step 4: Image Undistortion ===")
    dense_dir.mkdir(exist_ok=True)
    run([
        "colmap", "image_undistorter",
        "--image_path", str(image_dir),
        "--input_path", str(sparse_dir / "0"),
        "--output_path", str(dense_dir),
        "--output_type", "COLMAP",
    ], "Undistorting images")

    print(f"\n✓ Preprocessing complete. Output in: {output_dir}")
    print(f"  Sparse model: {sparse_dir}/0/")
    print(f"  Dense (undistorted): {dense_dir}/")


def extract_gps(image_dir: Path) -> dict:
    """Extract GPS coordinates from drone photo EXIF (DJI standard)."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
    except ImportError:
        print("  Warning: Pillow not installed, skipping GPS extraction")
        return {}

    gps_data = {}
    for img_path in sorted(image_dir.glob("*.[jJ][pP][gG]")) + \
                     sorted(image_dir.glob("*.[jJ][pP][eE][gG]")) + \
                     sorted(image_dir.glob("*.[dD][nN][gG]")):
        try:
            with Image.open(img_path) as img:
                exif = img._getexif()
                if exif is None:
                    continue

                for tag_id, value in exif.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == "GPSInfo":
                        gps = {}
                        for gps_id in value:
                            gps_tag = GPSTAGS.get(gps_id, gps_id)
                            gps[gps_tag] = value[gps_id]

                        lat = gps.get("GPSLatitude")
                        lat_ref = gps.get("GPSLatitudeRef", "N")
                        lon = gps.get("GPSLongitude")
                        lon_ref = gps.get("GPSLongitudeRef", "E")
                        alt = gps.get("GPSAltitude", 0)

                        if lat and lon:
                            lat_val = lat[0] + lat[1]/60 + lat[2]/3600
                            lon_val = lon[0] + lon[1]/60 + lon[2]/3600
                            if lat_ref == "S":
                                lat_val = -lat_val
                            if lon_ref == "W":
                                lon_val = -lon_val

                            gps_data[img_path.name] = {
                                "lat": round(lat_val, 7),
                                "lon": round(lon_val, 7),
                                "alt": float(alt) if alt else 0,
                            }
        except Exception:
            pass

    return gps_data


def export_for_gsplat(colmap_dir: Path, output_dir: Path):
    """
    Convert COLMAP sparse output to the format expected by gsplat/3DGS training.
    """
    # The original 3DGS and gsplat both read COLMAP sparse format directly,
    # so just symlink/copy and write a dataset config
    sparse_model = colmap_dir / "sparse" / "0"
    if not sparse_model.exists():
        print("  Error: Sparse model not found. Run preprocess() first.")
        return

    gsplat_dir = output_dir / "gsplat_input"
    gsplat_dir.mkdir(parents=True, exist_ok=True)

    # Copy sparse model
    import shutil
    dest = gsplat_dir / "sparse" / "0"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copytree(str(sparse_model), str(dest))

    # Copy images (or use dense/undistorted)
    dense_images = colmap_dir / "dense" / "images"
    image_dest = gsplat_dir / "images"
    if dense_images.exists() and not image_dest.exists():
        shutil.copytree(str(dense_images), str(image_dest))

    # Dataset config
    config = {
        "format": "colmap",
        "colmap_path": str(dest.parent),
        "images_path": str(image_dest) if image_dest.exists() else "",
    }
    with open(gsplat_dir / "dataset.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n✓ GSplat training data ready: {gsplat_dir}")
    print(f"  Run gsplat training with: --data {gsplat_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Preprocess drone photos with COLMAP for 3DGS training"
    )
    parser.add_argument("input", help="Directory containing drone photos")
    parser.add_argument("-o", "--output", default="./colmap_output", help="Output directory")
    parser.add_argument("--extract-gps", action="store_true", help="Extract GPS from EXIF")
    parser.add_argument("--skip-colmap", action="store_true", help="Skip COLMAP (assume already run)")

    args = parser.parse_args()
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    if not input_dir.is_dir():
        print(f"Error: {input_dir} is not a directory")
        sys.exit(1)

    num_images = len(list(input_dir.glob("*.[jJ][pP][gG]")) +
                     list(input_dir.glob("*.[jJ][pP][eE][gG]")) +
                     list(input_dir.glob("*.[dD][nN][gG]")))
    print(f"Found {num_images} images in {input_dir}")

    if not args.skip_colmap:
        if not check_colmap():
            print("\n⚠️  COLMAP not found!")
            print("  Install: brew install colmap    (macOS)")
            print("       or: apt install colmap     (Ubuntu)")
            print("       or: https://colmap.github.io/install.html")
            print("\n  Proceeding with GPS extraction only...")

        try:
            preprocess(input_dir, output_dir)
        except RuntimeError as e:
            print(f"\n⚠️  COLMAP failed: {e}")
            print("  This is common with drone nadir imagery.")
            print("  Try DroneSplat's DUSt3R approach for better results.")

    if args.extract_gps:
        print("\n=== GPS Extraction ===")
        gps_data = extract_gps(input_dir)

        if gps_data:
            gps_path = output_dir / "gps.json"
            with open(gps_path, "w") as f:
                json.dump(gps_data, f, indent=2)
            print(f"  Found GPS in {len(gps_data)}/{num_images} images → {gps_path}")

            # Calculate scene center
            lats = [d["lat"] for d in gps_data.values()]
            lons = [d["lon"] for d in gps_data.values()]
            alts = [d["alt"] for d in gps_data.values()]
            print(f"  Scene center: {sum(lats)/len(lats):.6f}, {sum(lons)/len(lons):.6f}")
            print(f"  Altitude range: {min(alts):.1f}m — {max(alts):.1f}m")
        else:
            print("  No GPS data found in images")

    # Export for gsplat
    if not args.skip_colmap:
        export_for_gsplat(output_dir, output_dir)

    print("\n=== Next Steps ===")
    print("  1. Train: ns-train gaussian-splatting --data colmap_output/gsplat_input/")
    print("  2. Export: ns-export gaussian-splatting --output-dir exports/")
    print("  3. Convert: python convert.py exports/point_cloud.ply -o scene.splat")
    print("  4. View: Drop scene.splat into GeoSplat viewer!")


if __name__ == "__main__":
    main()
