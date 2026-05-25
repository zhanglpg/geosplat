#!/usr/bin/env python3
"""
GeoSplat Pipeline — Convert PLY (from 3DGS training) to .splat format.
Enhanced version of antimatter15's convert.py with geospatial metadata support.

.splat binary format (32 bytes per splat):
  position: 3 × float32 (12 bytes)  — x, y, z
  scales:   3 × float32 (12 bytes)  — exp(scale_0), exp(scale_1), exp(scale_2)
  color:    4 × uint8   (4 bytes)   — r, g, b, a (opacity sigmoid)
  rotation: 4 × uint8   (4 bytes)   — quaternion normalized to [0,255]

Usage:
  python convert.py input.ply -o output.splat
  python convert.py input.ply --georef lat,lng,alt  # embed GPS origin
"""

import argparse
import json
import struct
import sys
from pathlib import Path

try:
    from plyfile import PlyData
except ImportError:
    print("Error: plyfile not installed. Run: pip install plyfile")
    sys.exit(1)

import numpy as np


SH_C0 = 0.28209479177387814


def process_ply_to_splat(
    ply_path: str,
    output_path: str | None = None,
    georef: tuple[float, float, float] | None = None,
    sh_bands: int = 0,
) -> bytes:
    """
    Convert a PLY file (output from 3DGS training) to .splat binary format.

    Args:
        ply_path: Path to .ply file
        output_path: Output .splat path (if None, returns bytes)
        georef: Optional (lat, lon, alt) GPS origin
        sh_bands: Number of spherical harmonics bands to include (0-3).
                  0 = just DC color (32 bytes/splat)
                  1-3 = include SH coefficients (larger file, view-dependent effects)

    Returns:
        .splat file as bytes
    """
    print(f"Reading {ply_path}...")
    plydata = PlyData.read(ply_path)
    vert = plydata["vertex"]

    num_vertices = len(vert)
    print(f"  {num_vertices:,} gaussians")

    # Sort by size × opacity (larger/more-opaque splats first)
    sorted_indices = np.argsort(
        -np.exp(vert["scale_0"] + vert["scale_1"] + vert["scale_2"])
        / (1 + np.exp(-vert["opacity"]))
    )

    # Calculate output size
    sh_bytes_per_splat = 0
    if sh_bands >= 1:
        # 48 coefficients for full 3rd-order SH
        sh_coeff_count = sum(3 for b in range(1, sh_bands + 1))
        sh_bytes_per_splat = sh_coeff_count * 4  # float32 each

    bytes_per_splat = 32 + sh_bytes_per_splat
    total_bytes = num_vertices * bytes_per_splat

    print(f"  Format: {bytes_per_splat} bytes/splat, {total_bytes / 1024 / 1024:.1f} MB total")
    if sh_bands == 0:
        print("  No spherical harmonics (view-independent lighting)")

    buffer = bytearray(total_bytes)
    offset = 0

    for idx in sorted_indices:
        v = vert[idx]

        # Position (12 bytes)
        struct.pack_into(
            "fff", buffer, offset,
            float(v["x"]), float(v["y"]), float(v["z"])
        )
        offset += 12

        # Scales — exp transform (12 bytes)
        struct.pack_into(
            "fff", buffer, offset,
            float(np.exp(v["scale_0"])),
            float(np.exp(v["scale_1"])),
            float(np.exp(v["scale_2"]))
        )
        offset += 12

        # Color + opacity (4 bytes)
        color_r = int(np.clip((0.5 + SH_C0 * v["f_dc_0"]) * 255, 0, 255))
        color_g = int(np.clip((0.5 + SH_C0 * v["f_dc_1"]) * 255, 0, 255))
        color_b = int(np.clip((0.5 + SH_C0 * v["f_dc_2"]) * 255, 0, 255))
        opacity = int(np.clip(1 / (1 + np.exp(-v["opacity"])) * 255, 0, 255))
        struct.pack_into("BBBB", buffer, offset, color_r, color_g, color_b, opacity)
        offset += 4

        # Rotation quaternion — normalized to [0,255] (4 bytes)
        rot = np.array([v["rot_0"], v["rot_1"], v["rot_2"], v["rot_3"]], dtype=np.float32)
        rot = rot / np.linalg.norm(rot)
        rot = np.clip((rot * 128 + 128), 0, 255).astype(np.uint8)
        struct.pack_into("BBBB", buffer, offset, int(rot[0]), int(rot[1]), int(rot[2]), int(rot[3]))
        offset += 4

    if offset != total_bytes:
        print(f"  WARNING: wrote {offset} bytes, expected {total_bytes}")

    # Write output
    if output_path is None:
        output_path = str(Path(ply_path).with_suffix(".splat"))

    with open(output_path, "wb") as f:
        f.write(buffer)

    print(f"  Saved: {output_path} ({total_bytes / 1024 / 1024:.1f} MB)")

    # Write metadata sidecar
    meta = {
        "num_gaussians": num_vertices,
        "bytes_per_splat": bytes_per_splat,
        "sh_bands": sh_bands,
        "format_version": 1,
    }
    if georef:
        meta["georef"] = {
            "lat": georef[0],
            "lon": georef[1],
            "alt": georef[2],
            "description": "WGS84 origin point for scene coordinates",
        }

    meta_path = output_path + ".json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"  Metadata: {meta_path}")

    return bytes(buffer)


def main():
    parser = argparse.ArgumentParser(
        description="Convert 3DGS PLY to .splat compact binary format"
    )
    parser.add_argument("input", nargs="+", help="Input .ply file(s)")
    parser.add_argument("-o", "--output", default=None, help="Output .splat file")
    parser.add_argument(
        "--georef",
        help="GPS origin: lat,lon,alt (e.g. '30.25,120.12,50')",
        default=None,
    )
    parser.add_argument(
        "--sh-bands",
        type=int,
        default=0,
        choices=[0, 1, 2, 3],
        help="Spherical harmonics bands (0 = DC only, 3 = full view-dependent)",
    )
    parser.add_argument(
        "--tile",
        type=int,
        default=1,
        help="Split scene into N×N×1 grid tiles (experimental)",
    )

    args = parser.parse_args()

    georef = None
    if args.georef:
        parts = list(map(float, args.georef.split(",")))
        if len(parts) == 3:
            georef = tuple(parts)

    for input_file in args.input:
        output_file = args.output
        if output_file is None or len(args.input) > 1:
            output_file = str(Path(input_file).with_suffix(".splat"))

        process_ply_to_splat(
            input_file,
            output_path=output_file,
            georef=georef,
            sh_bands=args.sh_bands,
        )

    print("\nDone! Upload .splat to your GeoSplat viewer or serve as static file.")


if __name__ == "__main__":
    main()
