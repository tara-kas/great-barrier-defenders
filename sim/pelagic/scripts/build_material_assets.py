#!/usr/bin/env python3
"""Rebuild original tileable coral surface maps; no network needed.

The downloaded CC0 seabed scans are tracked as assets and are not regenerated.
Image coordinates run downwards, so OpenGL tangent-space normal +Y is produced
by negating the image-space Y tangent when converting a height gradient.
"""
from pathlib import Path
import argparse
import numpy as np
from PIL import Image


def normal_from_height(height, strength=3.5):
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * .5
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * .5
    normals = np.stack([-dx * strength, dy * strength, np.ones_like(height)], axis=-1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
    return np.uint8(np.clip((normals * .5 + .5) * 255, 0, 255))


def coral_surface(size=1024, seed=26, cells=28):
    """Tiny irregular calices with subtle raised rims, not coarse rocky noise."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:size, :size].astype(np.float32)
    xx /= size
    yy /= size
    nearest = np.full((size, size), 10., np.float32)
    rim_height = np.zeros((size, size), np.float32)
    for row in range(cells):
        for col in range(cells):
            cx = (col + .5 + .32 * (row % 2) + rng.uniform(-.17, .17)) / cells
            cy = (row + .5 + rng.uniform(-.17, .17)) / cells
            # Touch only a local patch; wrap indices to guarantee seamless maps.
            px, py = round(cx * size), round(cy * size)
            extent = round(size / cells * .80)
            xs = np.arange(px - extent, px + extent + 1)
            ys = np.arange(py - extent, py + extent + 1)
            local_y, local_x = np.meshgrid(ys / size - cy, xs / size - cx, indexing="ij")
            angle = np.arctan2(local_y, local_x)
            scale = rng.uniform(.84, 1.10)
            radial = np.sqrt(local_x ** 2 + local_y ** 2) * cells / scale
            radial *= 1 + .035 * np.sin(angle * 10 + row + col)
            rim = .22 * np.exp(-((radial - .285) / .055) ** 2)
            cup = -.13 * np.exp(-(radial / .18) ** 2)
            # Delicate radial septa visible only at close inspection distances.
            septa = .026 * np.cos(angle * 12) * np.exp(-((radial - .21) / .10) ** 2)
            ys_wrapped, xs_wrapped = ys % size, xs % size
            patch = np.ix_(ys_wrapped, xs_wrapped)
            rim_height[patch] += rim + cup + septa
            nearest[patch] = np.minimum(nearest[patch], radial)
    # Fine tissue grain is weak and lacks the coarse spikes of rocky noise.
    grain = rng.normal(0., .008, (size, size)).astype(np.float32)
    height = rim_height + grain
    roughness = np.clip(.78 + .08 * np.exp(-(nearest / .22) ** 2) + grain, .70, .92)
    detail = np.clip(.93 + height * .12, .84, .98)
    tint = np.stack([detail, detail * .985, detail * .96], axis=-1)
    return height, np.uint8(roughness * 255), np.uint8(tint * 255)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent.parent / "assets/materials/coral")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    height, roughness, diffuse = coral_surface()
    Image.fromarray(normal_from_height(height)).save(args.output / "coral_normal_gl.png")
    Image.fromarray(roughness).save(args.output / "coral_roughness.png")
    Image.fromarray(diffuse).save(args.output / "coral_albedo_detail.png")
    height_image = np.uint16(np.clip((height + .2) / .6, 0, 1) * 65535)
    Image.fromarray(height_image).save(args.output / "coral_height.png")
    print(f"Wrote four seamless 1024px coral surface maps to {args.output}")


if __name__ == "__main__":
    main()
