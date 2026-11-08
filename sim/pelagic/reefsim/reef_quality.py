"""Offline scanned reef scenery, with a bounded camera/worksite detail budget.

Both sources are bundled Smithsonian specimens; their provenance is retained in
assets/pocillopora and assets/corals. The tissue colours and weathering are
artistic scenario states, not biological measurements. No scan is flattened
into a plate, stretched into a spike, or given a second disconnected crown.
"""
from __future__ import annotations

import math
import random

from .pocillopora_scan import generate_pocillopora_scan, _load as _load_pocillopora
from .scanned_coral import generate_scanned_coral, _load as _load_acropora
from .reef_tissue import PHENOTYPES, tissue_color


def _counts():
    return {"acropora": len(_load_acropora("acropora_secale")["counts"]),
            "standard": len(_load_pocillopora("standard")["counts"]),
            "hero": len(_load_pocillopora("hero")["counts"])}


def plan_reef_quality(colonies, snapshot, config=None):
    """Return ID -> quality spec; author each mesh once, never every frame.

    Original seam-preserving UVs and 150k faces are reserved for colonies near
    operation sites. The rest retain coherent 15k/20k scanned branches with
    world-scale tissue microdetail instead of applying an atlas to decimated
    UV seams. Default additional scenery budget is 14 million triangles and
    at most 24 hero specimens. This includes dead colonies equally.

    Config render keys: reef_hero_colonies (0..48), reef_triangle_budget (int).
    Too-small budgets fail explicitly rather than silently omit reef cover.
    The function also works for registered non-contact colonies.
    """
    colonies = list(colonies)
    if len({c["id"] for c in colonies}) != len(colonies):
        raise ValueError("coral IDs must be unique")
    render = (config or {}).get("render", {})
    hero_limit = render.get("reef_hero_colonies", 24)
    budget = render.get("reef_triangle_budget", 14_000_000)
    if isinstance(hero_limit, bool) or not isinstance(hero_limit, int) or not 0 <= hero_limit <= 48:
        raise ValueError("reef_hero_colonies must be an integer from 0 to 48")
    if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
        raise ValueError("reef_triangle_budget must be a positive integer")
    triangles = _counts()
    if len(colonies) * min(triangles["acropora"], triangles["standard"]) > budget:
        raise ValueError("reef_triangle_budget cannot fit the requested scanned reef population")
    focus=set(render.get("quality_focus_ids",[]))
    anchors = [c["position"] for c in snapshot.get("corals", []) if not focus or c["id"] in focus]
    anchors += [(*p["center"],0.) for p in render.get("recovery_clearings",[])]
    if not focus:
        anchors += [c["position"] for c in snapshot.get("robots", []) if "position" in c]
    if not anchors:
        anchors = [(0., 0., 0.)]
    specs = {}
    for colony in colonies:
        seed = int(colony.get("seed", 26))
        position = colony["position"]
        distance, anchor = min((math.hypot(position[0]-p[0], position[1]-p[1]), i)
                               for i, p in enumerate(anchors))
        # Two real growth forms, modest coherent variation, many orientations.
        # Old morphology labels remain mission metadata, not a request to
        # squash a real skeletal specimen into an artificial disc.
        poci = colony.get("morphology") == "boulder" or seed % 5 < 3
        specs[colony["id"]] = {
            "asset": "pocillopora_damicornis" if poci else "acropora_secale",
            "detail": "standard", "material": "organic", "uv_mode": "microdetail",
            "phenotype": PHENOTYPES[seed % len(PHENOTYPES)],
            "health": colony["health"], "triangles": triangles["standard" if poci else "acropora"],
            "distance": distance, "anchor": anchor,
        }
    total = sum(spec["triangles"] for spec in specs.values())
    ordered = sorted(colonies, key=lambda c: (specs[c["id"]]["distance"], c["id"]))
    # Preserve coverage even at increased population density: first lower far
    # specimens to the cheaper complete scan, then spend spare faces nearby.
    for colony in reversed(ordered):
        spec = specs[colony["id"]]
        if total <= budget:
            break
        if spec["asset"] == "pocillopora_damicornis":
            total += triangles["acropora"] - spec["triangles"]
            spec.update(asset="acropora_secale", triangles=triangles["acropora"])
    # Round-robin nearest specimens around work sites, so a single dense patch
    # cannot consume every original-UV colony in a multi-robot mission.
    groups = {}
    for colony in ordered:
        groups.setdefault(specs[colony["id"]]["anchor"], []).append(colony)
    candidates = []
    while groups:
        for anchor in sorted(tuple(groups)):
            candidates.append(groups[anchor].pop(0))
            if not groups[anchor]:
                del groups[anchor]
    promoted = 0
    for colony in candidates:
        if promoted >= hero_limit:
            break
        spec = specs[colony["id"]]
        extra = triangles["hero"] - spec["triangles"]
        if total + extra <= budget:
            spec.update(asset="pocillopora_damicornis", detail="hero", material="tissue",
                        uv_mode="source_atlas", triangles=triangles["hero"])
            total += extra
            promoted += 1
    return specs


def generate_quality_coral(colony, spec):
    """Return {mesh, material, health, phenotype, asset, detail, uv_mode, triangles}.

    Bind material='tissue' with IsaacScene._bind_tissue(mesh, health, phenotype).
    Bind material='organic' to the existing vertex-colour/micro-normal material.
    All returned geometry is private mutable data, grounded at local Z=0, and
    fits the supplied radius/height; existing clearance envelopes stay valid.
    Bleaching preserves skeleton shape; dead weathered framework has lower
    relief and muted algal patches. Animation of rigid stony skeletons belongs
    to the substrate/current model rather than individual branch bending.
    """
    health = colony["health"]
    if health != spec["health"]:
        raise ValueError("quality plan health must match colony health")
    radius, height = float(colony["radius"]), float(colony["height"])
    seed = int(colony.get("seed", 26))
    if spec["asset"] == "pocillopora_damicornis":
        mesh = generate_pocillopora_scan(health, radius, height, seed,
                                         preserve_aspect=True, detail=spec["detail"])
    elif spec["asset"] == "acropora_secale":
        mesh = generate_scanned_coral(health, radius, height, seed, preserve_aspect=True)
    else:
        raise ValueError("quality plan references an unsupported scan")
    rng = random.Random(seed + 41893)
    sx, sy, sz = rng.uniform(.88, 1.04), rng.uniform(.88, 1.04), rng.uniform(.94, 1.04)
    bx, by = rng.uniform(-.065, .065), rng.uniform(-.065, .065)
    if health == "dead":
        sz *= .80
        bx += .10
    points = [(sx*x+bx*z, sy*y+by*z, sz*z) for x, y, z in mesh["points"]]
    low = min(p[2] for p in points)
    extent_radius = max(math.hypot(p[0], p[1]) for p in points)
    extent_height = max(p[2] for p in points)-low
    fit = min(1., radius/max(extent_radius, 1e-12), height/max(extent_height, 1e-12))
    mesh["points"] = [(x*fit, y*fit, (z-low)*fit) for x,y,z in points]
    normals = []
    for nx, ny, nz in mesh["normals"]:
        nx, ny, nz = nx/sx, ny/sy, (nz-bx*nx/sx-by*ny/sy)/sz
        length = math.hypot(nx, ny, nz)
        normals.append((nx/length, ny/length, nz/length))
    mesh["normals"] = normals
    if spec["uv_mode"] == "source_atlas":
        # Atlas includes calices, patchy tissue and roughness. Multiplying it
        # by another pigment would turn living white tissue dull brown.
        mesh["colors"] = [(1., 1., 1.)] * len(points)
    else:
        pigment = tissue_color(health, seed)
        residual = tissue_color("healthy", seed)
        phase = (seed % 97) * .37
        colors = []
        for point, old_color in zip(mesh["points"], mesh["colors"]):
            x, y, z = (v / radius for v in point)
            patch = .5 + .5 * math.sin(3.7*x + phase + 1.6*math.sin(3*y)) * math.cos(4.8*z-y)
            if health == "bleached_alive":
                # Residual tissue islands, particularly at the branch base;
                # these are pale living colonies, not uniform white skeletons.
                retained = .08 + .34 * max(0., (patch-.48)/.52)
                base = tuple(p*(1-retained)+r*retained for p,r in zip(pigment,residual))
            elif health == "dead":
                base = tuple(p*(.72+.45*patch) for p in pigment)
            else:
                base = tuple(p*(.84+.24*patch) for p in pigment)
            # Existing scan's calice-scale luminance is normalized per state
            # so a dark pigment is not applied twice.
            scan_luma = sum(old_color)/3
            scan_base = .82 if health == "bleached_alive" else .24 if health == "dead" else .38
            micro = max(.65, min(1.18, .72+.25*scan_luma/scan_base))
            colors.append(tuple(max(0., min(1., v*micro)) for v in base))
        mesh["colors"] = colors
        mesh["uvs"] = [(x*5., y*2.+z*5.) for x,y,z in mesh["points"]]
    return {"mesh": mesh, **{k: spec[k] for k in
            ("material", "health", "phenotype", "asset", "detail", "uv_mode")},
            "triangles": len(mesh["counts"])}
