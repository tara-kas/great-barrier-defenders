"""Deterministic reef-patch scenery, inspired by Indo-Pacific reef mosaics.

These extra colonies are visual context, not hidden mission targets or tall
unmodelled navigation obstacles. Registered colonies retain clear operating
space. This is an artistic reef, not a reconstruction of a surveyed location.
"""
from __future__ import annotations

import math
import random


def build_reef_scenery(config, snapshot):
    """Return a dense mosaic of clustered low colonies with contrasting zone cover.

    Record fields match the scene's ``generate_coral`` input, with a local
    position at the seabed. Use ``detail='low'`` when authoring these meshes.
    """
    rng = random.Random(int(snapshot.get("seed", config.get("seed", 26))) + 9031)
    world = snapshot.get("world", config.get("world", {}))
    width, length = float(world.get("width", 10)), float(world.get("length", 10))
    main = snapshot.get("corals", [])
    obstacles = snapshot.get("obstacles", [])
    result = []
    raw_density = float(config.get("render", {}).get("reef_density", 1.))
    density = min(1.5, max(.5, raw_density)) if math.isfinite(raw_density) else 1.
    populations = {"healthy": 240, "bleached_alive": 140, "dead": 70}

    for region in snapshot.get("regions", config.get("regions", [])):
        cx, cy = region.get("center", [0, 0])[:2]
        health = region.get("health", "dead")
        policy = region.get("policy", "avoid")
        count = round((50 if policy == "avoid" else populations.get(health, 70)) * density)
        radius = max(1.7, float(region.get("radius", 2)))
        # Cluster centres are deliberately asymmetric; no survey-grid motif.
        clusters = [(cx + rng.uniform(-.9, .9), cy + rng.uniform(-.9, .9)) for _ in range(7)]
        accepted = 0
        for attempt in range(count * 280):
            if accepted >= count:
                break
            kx, ky = clusters[rng.randrange(len(clusters))]
            x, y = rng.gauss(kx, .72), rng.gauss(ky, .72)
            if not (-width / 2 + .10 < x < width / 2 - .10 and
                    -length / 2 + .10 < y < length / 2 - .10):
                continue
            if math.hypot(x - cx, y - cy) > radius * 1.20:
                continue
            if health == "healthy":
                morphology = rng.choices(("branching", "plating", "boulder"), (.50, .32, .18))[0]
                scale = rng.uniform(.14, .29)
                height = rng.uniform(.16, .34) if morphology == "branching" else scale * rng.uniform(.55, .95)
                if morphology == "plating":
                    scale *= 1.16
                    height = rng.uniform(.11, .20)
            elif health == "bleached_alive":
                morphology = rng.choices(("branching", "plating", "boulder"), (.55, .25, .20))[0]
                scale = rng.uniform(.12, .25)
                height = rng.uniform(.14, .29) if morphology == "branching" else scale * .72
            else:
                morphology = rng.choices(("branching", "boulder", "plating"), (.65, .30, .05))[0]
                scale = rng.uniform(.11, .25)
                height = rng.uniform(.07, .19) if morphology == "branching" else scale * .38
                if policy == "avoid":
                    height *= .70
            # Main colonies have space for vehicle approach, opening jaws and
            # donor cutting. No decorative specimen can mask the operation.
            if any(math.hypot(x - c["position"][0], y - c["position"][1]) <
                   float(c.get("radius", .3)) + .18 + scale * .70 for c in main):
                continue
            if any(c.get("planting_point") and math.hypot(x - c["planting_point"][0], y - c["planting_point"][1]) < .22 + scale
                   for c in main):
                continue
            if any(math.hypot(x - o["position"][0], y - o["position"][1]) <
                   float(o.get("radius", .3)) + scale * .65 for o in obstacles):
                continue
            # Interlocking branches can have overlapping broad bounding discs,
            # while neighbouring stems and massive colonies stay separate.
            if any(math.hypot(x - c["position"][0], y - c["position"][1]) <
                   .46 * (scale + c["radius"]) for c in result):
                continue
            result.append({"id": f"scenery-{len(result):03d}",
                           "position": [x, y, _foundation_height(x, y, config, snapshot) - .012], "morphology": morphology,
                           "health": health, "radius": scale, "height": height,
                           "seed": 80000 + len(result) * 31 + int(config.get("seed", 26)),
                           "region_id": region["id"], "display_only": True})
            accepted += 1

    # The living patch continues beyond the experiment boundary, giving the
    # camera a reef horizon without surrounding everything in an even ring.
    for index in range(round(80 * density)):
        x = rng.uniform(-7.5, -1.2)
        y = rng.uniform(-7.5, -5.3) if index < round(48 * density) else rng.uniform(-5., -1.)
        if y > -5 and x > -5.4:
            x = rng.uniform(-7.5, -5.4)
        scale = rng.uniform(.24, .48)
        morphology = ("branching", "plating", "boulder")[index % 3]
        result.append({"id": f"scenery-{len(result):03d}", "position": [x, y, _foundation_height(x, y, config, snapshot) - .012],
                       "morphology": morphology, "health": "healthy", "radius": scale,
                       "height": rng.uniform(.25, .48) if morphology == "branching" else scale * .7,
                       "seed": 99000 + index * 43, "region_id": "living-extension", "display_only": True})
    return result


def _floor_height(x, y):
    """The same rippled sand surface used by the Isaac scene."""
    phase = x * 6.2 + .9 * math.sin(y * .7) + .3 * math.sin(x * .3)
    return (-.075 + .012 * math.sin(phase) + .004 * math.sin(phase * 2 + .6)
            + .022 * math.sin(x * .33 + .5) * math.cos(y * .28))


def _foundation_height(x, y, config, snapshot):
    """Shallow, connected reef pavement with scalloped sand-channel edges."""
    regions = snapshot.get("regions", config.get("regions", []))
    cover = 0.
    life = 0.
    for region in regions:
        cx, cy = region.get("center", [0, 0])[:2]
        distance = math.hypot(x - cx, y - cy)
        radius = float(region.get("radius", 2))
        # Overlapping irregular patches create continuous substrate, while
        # lower relief in damaged regions reads as eroded reef framework.
        edge = .21 * math.sin(x * 2.1 + y * .8) + .16 * math.sin(y * 2.9 - x * .4)
        amount = max(0., min(1., (radius * 1.43 + edge - distance) / .63))
        cover = max(cover, amount)
        if region.get("health") == "healthy":
            life = max(life, amount)
    # A broad, asymmetric living shelf continues beyond the SW boundary.
    southwest = max(0., min(1., (-x - 4.1) / .8)) * max(0., min(1., (1. - y) / 1.5))
    south = max(0., min(1., (-y - 4.2) / .7)) * max(0., min(1., (-x + 1.) / 1.5))
    cover = max(cover, southwest, south)
    life = max(life, southwest, south)
    # Meandering sandy channels expose the underlying sand, without creating
    # radial gaps or disconnected cookie-cutter discs around every colony.
    channel = abs(x + .38 * math.sin(y * .9) + .18 * math.sin(y * 2.4))
    cover *= .28 + .72 * max(0., min(1., (channel - .12) / .40))
    roughness = .5 + .25 * math.sin(x * 5.7 + y * 2.4) + .25 * math.cos(y * 6.1 - x * 1.3)
    relief = cover * (.040 + .025 * life + .025 * roughness)
    # Every prepared mount remains visible and accessible. Its shallow apron
    # rejoins this pavement gradually, rather than growing new radial roots.
    for coral in snapshot.get("corals", []):
        planting = coral.get("planting_point")
        if planting:
            distance = math.hypot(x - planting[0], y - planting[1])
            relief *= max(0., min(1., (distance - .20) / .28))
    return min(.055, _floor_height(x, y) + .001 + relief)


def build_reef_foundation(config, snapshot, *, resolution=176):
    """Return one indexed, low relief reef-pavement mesh, in world coordinates.

    The surface follows the actual seabed. Sand channels and weathered dead
    framework connect low colonies into reef patches; no collision is implied.
    Heights stay below the 8 cm planting mounts. Vertex colour distinguishes
    muted living crust from exposed calcareous/algal substrate.
    """
    if not isinstance(resolution, int) or resolution < 16 or resolution > 512:
        raise ValueError("foundation resolution must be an integer from 16 to 512")
    world = snapshot.get("world", config.get("world", {}))
    width = float(world.get("width", 10)) + 5.5
    length = float(world.get("length", 10)) + 5.5
    mesh = {key: [] for key in ("points", "normals", "colors", "uvs", "counts", "indices")}
    step_x, step_y = width / resolution, length / resolution
    regions = snapshot.get("regions", config.get("regions", []))
    heights = []
    for row in range(resolution + 1):
        y = -length / 2 + row * step_y
        line = []
        for col in range(resolution + 1):
            x = -width / 2 + col * step_x
            z = _foundation_height(x, y, config, snapshot)
            line.append(z)
            mesh["points"].append((x, y, z))
            closest = min(regions, key=lambda r: math.hypot(x-r["center"][0], y-r["center"][1])) if regions else {}
            health = closest.get("health", "dead")
            color = (.32, .34, .22) if health == "healthy" else ((.49, .47, .37) if health == "bleached_alive" else (.31, .34, .27))
            tint = .91 + .09 * math.sin(x * 4.2 + y * 5.3) * math.cos(y * 3.1)
            # At exposed channel edges the crust converges to the sand tone.
            coverage = max(0., min(1., (z - _floor_height(x, y) - .001) / .025))
            sand = (.51, .48, .36)
            mesh["colors"].append(tuple((sand[i]*(1-coverage) + color[i]*coverage)*tint for i in range(3)))
            mesh["uvs"].append((x * 1.7, y * 1.7))
        heights.append(line)
    for row in range(resolution + 1):
        for col in range(resolution + 1):
            lo_x, hi_x = max(0, col-1), min(resolution, col+1)
            lo_y, hi_y = max(0, row-1), min(resolution, row+1)
            dx = (heights[row][hi_x] - heights[row][lo_x]) / ((hi_x-lo_x)*step_x)
            dy = (heights[hi_y][col] - heights[lo_y][col]) / ((hi_y-lo_y)*step_y)
            norm = math.sqrt(dx*dx+dy*dy+1)
            mesh["normals"].append((-dx/norm, -dy/norm, 1/norm))
            if row < resolution and col < resolution:
                a = row * (resolution+1) + col
                mesh["counts"].append(4)
                mesh["indices"].extend((a, a+1, a+resolution+2, a+resolution+1))
    return mesh
