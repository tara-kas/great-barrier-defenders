"""Bundled Smithsonian Pocillopora damicornis scan; standard-library runtime.

The scan is of a dried museum specimen, USNM 46926, not living tissue or the
genets from the contact-recovery experiment. Geometry supplies species-labelled
skeletal morphology; health, genotype and living pigmentation remain scenario
metadata. See docs/POCILLOPORA_SCAN.md for source, license and conversion.
"""
from functools import lru_cache
import gzip
import json
import math
from pathlib import Path
import random


ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "pocillopora"


@lru_cache(maxsize=2)
def _load(detail="standard"):
    if detail not in ("standard","hero"):
        raise ValueError("detail must be standard or hero")
    name = "pocillopora_damicornis_hero.json.gz" if detail == "hero" else "pocillopora_damicornis_20k.json.gz"
    with gzip.open(ASSET_ROOT / name, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def source_dimensions(detail="standard"):
    """Unscaled skeleton dimensions, metres, after centring and Z grounding."""
    source = _load(detail)
    return {"radius": source["source_radius"], "height": source["source_height"],
            "height_radius_ratio": source["source_height"] / source["source_radius"],
            "specimen": source["source_specimen"]}


def texture_files():
    """Optional original scan detail maps; sampled vertex colours are bundled."""
    return {"base_color": str(ASSET_ROOT / "pocillopora_basecolor.jpg"),
            "normal": str(ASSET_ROOT / "pocillopora_normal.png")}


def generate_pocillopora_scan(health, radius, height, seed=0, *, preserve_aspect=True,
                             preserve_colors=False, detail="standard"):
    """Return indexed points/normals/colors/uvs/counts/indices for one colony.

    By default uniformly scale the actual specimen to fit both the requested
    radius and height, preserving its natural compact form. Explicitly setting
    preserve_aspect=False independently fits both extents for a documented
    artistic proxy. Every call returns independent mutable data. Seed supplies
    only yaw and healthy pigment variation, never new skeletal geometry.
    """
    if health not in ("healthy", "bleached_alive", "dead"):
        raise ValueError("health must be healthy, bleached_alive or dead")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
           not math.isfinite(value) or value <= 0 for value in (radius, height)):
        raise ValueError("radius and height must be finite positive numbers")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    source = _load(detail)
    if preserve_aspect:
        scale = min(radius / source["source_radius"], height / source["source_height"])
        radius, height = source["source_radius"] * scale, source["source_height"] * scale
    rng = random.Random(seed)
    angle = rng.uniform(-math.pi, math.pi)
    cosine, sine = math.cos(angle), math.sin(angle)
    pigment = (rng.choice(((.62, .28, .18), (.46, .22, .54), (.22, .47, .35), (.64, .43, .20)))
               if health == "healthy" else (.86, .82, .70) if health == "bleached_alive" else (.25, .29, .19))
    points, normals, colors = [], [], []
    for point, normal, color in zip(source["points"], source["normals"], source["colors"]):
        x, y, z = point[0] * radius, point[1] * radius, point[2] * height
        points.append((cosine * x - sine * y, sine * x + cosine * y, z))
        nx, ny, nz = normal[0] / radius, normal[1] / radius, normal[2] / height
        size = math.hypot(nx, ny, nz)
        normals.append(((cosine * nx - sine * ny) / size,
                        (sine * nx + cosine * ny) / size, nz / size))
        # Preserve the specimen's calice-scale luminance variation under a
        # living/bleached/dead scenario tint; no fluorescent colour is baked.
        detail = .58 + .62 * (.30 * color[0] + .59 * color[1] + .11 * color[2])
        colors.append(tuple(color) if preserve_colors else tuple(min(1., c * detail) for c in pigment))
    return {"points": points, "normals": normals, "colors": colors,
            "uvs": [tuple(uv) for uv in source["uvs"]],
            "counts": source["counts"][:], "indices": source["indices"][:]}
