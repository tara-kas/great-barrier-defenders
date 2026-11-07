"""Offline Smithsonian CC0 coral scan geometry, using only the standard library.

This is scenery, not a living-tissue or specimen-identification model. Source
geometry and provenance are bundled in assets/corals; no runtime downloads or
mesh-conversion packages are needed. See docs/SCANNED_CORALS.md.
"""
from __future__ import annotations

import gzip
import json
import math
import random
from functools import lru_cache
from pathlib import Path

_ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "corals"
_ASSETS = {"acropora_secale": "acropora_secale_15k.json.gz"}


def available_assets():
    return tuple(_ASSETS)


@lru_cache(maxsize=2)
def _load(asset):
    if asset not in _ASSETS:
        raise ValueError(f"Unknown coral scan: {asset}")
    with gzip.open(_ASSET_ROOT / _ASSETS[asset], "rt", encoding="utf-8") as handle:
        return json.load(handle)


def texture_files(asset="acropora_secale"):
    """Optional original scan textures; sampled colours require neither file.

    UVs are transferred from the closest source vertices during decimation,
    so these textures are best suited to background specimens, not macro QA.
    """
    _load(asset)
    return {"base_color": str(_ASSET_ROOT / "acropora_secale_basecolor.jpg"),
            "normal": str(_ASSET_ROOT / "acropora_secale_normal.png")}


def generate_scanned_coral(health, radius, height, seed=0, *,
                           asset="acropora_secale", preserve_colors=False,
                           preserve_aspect=False):
    """Return organic.generate_coral-compatible indexed mesh attributes.

    ``radius`` is an exact maximum horizontal radius; ``height`` is the exact
    Z extent. With ``preserve_aspect=True`` the original scan is uniformly
    scaled to fit both bounds instead. Seed changes yaw and healthy pigment,
    never scan topology. Colours are scenario pigments with retained scan
    shading; ``preserve_colors=True`` returns dry museum-specimen colours.
    """
    if health not in ("healthy", "bleached_alive", "dead"):
        raise ValueError("health must be healthy, bleached_alive or dead")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
           not math.isfinite(value) or value <= 0 for value in (radius, height)):
        raise ValueError("radius and height must be finite positive dimensions")
    source = _load(asset)
    rng = random.Random(int(seed))
    yaw = rng.uniform(-math.pi, math.pi)
    cosine, sine = math.cos(yaw), math.sin(yaw)
    if preserve_aspect:
        scale = min(radius / source["source_radius"], height / source["source_height"])
        radius, height = source["source_radius"] * scale, source["source_height"] * scale
    if health == "healthy":
        # Natural warm orange, dusky purple, teal and ochre tissue. These are
        # artistic living pigments, not the original dried specimen's colour.
        pigment = rng.choice(((.63, .31, .12), (.39, .20, .43),
                              (.18, .48, .40), (.60, .43, .22)))
    elif health == "bleached_alive":
        pigment = (.86, .80, .67)
    else:
        pigment = (.32, .30, .23)
    points, normals, colors = [], [], []
    for point, normal, color in zip(source["points"], source["normals"], source["colors"]):
        x, y, z = point[0] * radius, point[1] * radius, point[2] * height
        points.append((cosine * x - sine * y, sine * x + cosine * y, z))
        nx, ny, nz = normal[0] / radius, normal[1] / radius, normal[2] / height
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        normals.append(((cosine * nx - sine * ny) / length,
                        (sine * nx + cosine * ny) / length, nz / length))
        brightness = .68 + .48 * (.30 * color[0] + .59 * color[1] + .11 * color[2])
        colors.append(tuple(color) if preserve_colors else
                      tuple(min(1., channel * brightness) for channel in pigment))
    return {"points": points, "normals": normals, "colors": colors,
            "uvs": [tuple(uv) for uv in source["uvs"]],
            "counts": source["counts"][:], "indices": source["indices"][:]}
