"""Seeded porous limestone boulders with conservative obstacle bounds.

These are visual reef-substrate approximations rather than geological scans.
The mesh rests on Z=0, fits the supplied horizontal radius and height, and is
closed underneath. Rounded asymmetric lobes, shallow erosion pits and damp
surface variation avoid identical smooth egg-shaped outcrops. The scene can
bind its bundled limestone PBR material to these standard mesh attributes.
"""
from __future__ import annotations

import math
import random


def _dimension(value, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) or value <= 0 or value > 100.):
        raise ValueError(f"{name} must be finite and in (0,100] metres")
    return float(value)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _unit(vector):
    size = math.sqrt(sum(v*v for v in vector))
    return tuple(v / size for v in vector) if size > 1e-14 else (0., 0., 1.)


def generate_reef_rock(radius, height, seed, detail="medium"):
    """Return indexed mesh data for a bounded, anchored limestone boulder.

    ``medium`` has 2,407 vertices; ``low`` has 189. Units are metres, Z-up.
    Radius is the maximum XY distance from the origin, including surface
    erosion. Height is the maximum Z value. The footprint is deliberately
    contained in the planner's circular obstacle, without extra mesh lobes
    outside that envelope. Topology stays deterministic for a given detail.
    """
    radius, height = _dimension(radius, "radius"), _dimension(height, "height")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if detail not in ("medium", "low"):
        raise ValueError("detail must be medium or low")
    sectors, rings = (64, 36) if detail == "medium" else (16, 10)
    rng = random.Random(seed)
    phases = [rng.uniform(-math.pi, math.pi) for _ in range(5)]
    theta_max = 2.32 + rng.uniform(-.07, .07)
    bottom_cos = math.cos(theta_max)
    # Large-scale shape and pits are continuous functions on the sphere;
    # neighbouring vertices never receive independent noisy displacements.
    pits = []
    for _ in range(12 if detail == "medium" else 4):
        theta, phi = rng.uniform(.32, theta_max - .12), rng.uniform(0., math.tau)
        center = (math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta))
        pits.append((center, rng.uniform(.10, .22), rng.uniform(.025, .065)))

    def surface(theta, phi):
        sine, cosine = math.sin(theta), math.cos(theta)
        cp, sp = math.cos(phi), math.sin(phi)
        direction = (sine * cp, sine * sp, cosine)
        erosion = 0.
        for center, width, depth in pits:
            separation = sum((direction[i] - center[i]) ** 2 for i in range(3))
            erosion += depth * math.exp(-separation / (width * width))
        lobe = .105 * math.sin(3 * phi + phases[0]) * sine
        lobe += .065 * math.cos(5 * phi + phases[1]) * sine * sine
        # Smooth absolute-value ridges give a rounded block-like silhouette,
        # with different broad faces rather than a perfect ellipsoid.
        facet = math.sqrt(math.cos(2 * phi + phases[2]) ** 2 + .09)
        radial = sine * (1. + lobe - .075 * facet * sine - erosion)
        radial *= 1. + .035 * math.sin(theta * 6 + phi * 2 + phases[3]) * sine
        z = (cosine - bottom_cos) / (1. - bottom_cos)
        distortion = .15 * math.sin(phi * 3 + phases[4]) * sine - erosion * 1.8
        z += z * (1. - z) * distortion
        # Offset upper faces relative to the footprint, so every boulder does
        # not share the same centred dome even before its surface is textured.
        offset_x = .13 * math.cos(phases[1]) * z * z
        offset_y = .13 * math.sin(phases[2]) * z * z
        return (radial * cp + offset_x, radial * sp + offset_y, z), erosion

    # Normalize the sampled footprint once. Normals use the same anisotropic
    # transform, and the bounded height function already has top1/base0.
    top, _ = surface(0., 0.)
    raw_points, parameters = [top], [(0., 0.)]
    erosion_values = [0.]
    for row in range(1, rings + 1):
        theta = row / rings * theta_max
        for column in range(sectors + 1):
            phi = column / sectors * math.tau
            point, erosion = surface(theta, phi)
            raw_points.append(point)
            parameters.append((theta, phi))
            erosion_values.append(erosion)
    extent = max(math.hypot(p[0], p[1]) for p in raw_points)
    xy_scale = radius / extent
    points, normals, colors, uvs = [], [], [], []
    epsilon = 1e-5
    for point, (theta, phi), erosion in zip(raw_points, parameters, erosion_values):
        p = (point[0] * xy_scale, point[1] * xy_scale, max(0., min(1., point[2])) * height)
        points.append(p)
        if theta == 0.:
            normal = (0., 0., 1.)
        else:
            a, _ = surface(max(0., theta - epsilon), phi)
            b, _ = surface(min(theta_max, theta + epsilon), phi)
            c, _ = surface(theta, phi - epsilon)
            d, _ = surface(theta, phi + epsilon)
            tangent_theta = ((b[0] - a[0]) * xy_scale, (b[1] - a[1]) * xy_scale,
                             (b[2] - a[2]) * height)
            tangent_phi = ((d[0] - c[0]) * xy_scale, (d[1] - c[1]) * xy_scale,
                           (d[2] - c[2]) * height)
            normal = _unit(_cross(tangent_theta, tangent_phi))
        normals.append(normal)
        variation = .88 + .11 * math.sin(phi * 2 + theta * 4 + phases[0])
        variation += .055 * math.sin(phi * 7 - theta * 5 + phases[3])
        damp = 1. - .12 * (1. - point[2]) - min(.16, erosion)
        colors.append(tuple(max(0., min(1., channel * variation * damp)) for channel in (.46, .43, .33)))
        # Cylindrical side UVs have an approximately 2m physical repeat.
        uvs.append((phi * radius / 2., p[2] / 2.))

    counts, indices = [], []

    def face(*ids):
        counts.append(len(ids))
        indices.extend(ids)

    for column in range(sectors):
        face(0, 1 + column, 1 + column + 1)
    for row in range(rings - 1):
        a = 1 + row * (sectors + 1)
        b = a + sectors + 1
        for column in range(sectors):
            face(a + column, b + column, b + column + 1, a + column + 1)
    # A separate normal seam closes the flat underside, keeping side normals
    # smooth while guaranteeing that a rock rests on its authored origin.
    side_base = 1 + (rings - 1) * (sectors + 1)
    cap_base = len(points)
    for column in range(sectors + 1):
        p = points[side_base + column]
        points.append((p[0], p[1], 0.))
        normals.append((0., 0., -1.))
        colors.append((.32, .31, .24))
        uvs.append((p[0] / 2., p[1] / 2.))
    center = len(points)
    points.append((0., 0., 0.))
    normals.append((0., 0., -1.))
    colors.append((.32, .31, .24))
    uvs.append((0., 0.))
    for column in range(sectors):
        face(center, cap_base + column + 1, cap_base + column)
    return {"points": points, "normals": normals, "colors": colors, "uvs": uvs,
            "counts": counts, "indices": indices}
