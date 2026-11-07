"""Procedural Pocillopora-inspired colony and contact-cutting geometry.

The supplied study photograph informs stout, blunt branching and conspicuous
recessed calices. This is an artistic morphology approximation, not a specimen
scan or a taxonomic identification model. Living and bleached colonies share
structure; bleaching changes tissue appearance without removing the calices.
The contact cutting preserves the existing lower 75 mm grasp/contact geometry.
"""
from __future__ import annotations

import math
import random

from .organic import _Builder, _curve, _unit, _cross, _add, _sub, _mul, _mix, generate_fragment


def _validate(health, radius, height, seed):
    if health not in ("healthy", "bleached_alive", "dead"):
        raise ValueError("Unsupported coral health")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
           for v in (radius, height)):
        raise ValueError("radius and height must be finite positive dimensions")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")


def _palette(health, seed):
    if health == "bleached_alive":
        return (.85, .80, .70), (.93, .86, .78)
    if health == "dead":
        return (.26, .28, .19), (.32, .31, .22)
    base = ((.56, .35, .19), (.56, .30, .34), (.52, .40, .22), (.49, .28, .21))[seed % 4]
    return base, _mix(base, (.82, .69, .60), .42)


def _calice(builder, anchor, normal, tangent, radius, color, health):
    start = len(builder.data["points"])
    builder.calice(anchor, normal, tangent, radius, color)
    if health == "bleached_alive":
        # Warm tissue-lined recesses, rather than uniformly black holes in a
        # chalk skeleton. Transparency/SSS belongs to the consuming material.
        for i in range(start, len(builder.data["colors"]) - 1):
            builder.data["colors"][i] = _mix(builder.data["colors"][i], (.91, .83, .77), .22)
        builder.data["colors"][-1] = (.70, .62, .57)


def _blunt_branch(builder, control, radius, base, tip, phase, health,
                  segments=10, sides=12, calices=9):
    """Stout tapered branch with a rounded cap, rather than a pointed tip."""
    rows, frames = [], []
    previous_u = None
    for row in range(segments + 1):
        t = row / segments
        center, tangent = _curve(control, t)
        if previous_u is None:
            reference = (1., 0., 0.) if abs(tangent[2]) > .8 else (0., 0., 1.)
            u = _unit(_cross(tangent, reference))
        else:
            u = _unit(_sub(previous_u, _mul(tangent, sum(previous_u[i] * tangent[i] for i in range(3)))))
        v = _unit(_cross(tangent, u))
        previous_u = u
        r = radius * (1. - .24 * t)
        color = _mix(base, tip, max(0., (t - .60) / .40) * .55)
        ring = []
        for column in range(sides + 1):
            angle = column / sides * math.tau
            radial = _add(_mul(u, math.cos(angle)), _mul(v, math.sin(angle)))
            # Shallow, rounded verrucae and tissue relief—not sharp thorns.
            relief = 1. + .055 * math.cos(4 * angle + phase) * math.sin(t * 12 + phase) ** 2
            normal = _unit(_add(radial, _mul(tangent, .10)))
            tint = .91 + .09 * (.5 + .5 * math.sin(angle * 7 + t * 15 + phase))
            ring.append(builder.vertex(_add(center, _mul(radial, r * relief)), normal,
                                       _mul(color, tint), (column / sides, t * 2.)))
        rows.append(ring)
        frames.append((center, tangent, u, v, r))
    end, tangent, u, v, r = frames[-1]
    # Hemisphere rings keep the crown blunt even at oblique camera angles.
    for cap in range(1, 4):
        angle = cap / 4 * math.pi / 2
        ring = []
        for column in range(sides + 1):
            around = column / sides * math.tau
            radial = _add(_mul(u, math.cos(around)), _mul(v, math.sin(around)))
            normal = _add(_mul(radial, math.cos(angle)), _mul(tangent, math.sin(angle)))
            ring.append(builder.vertex(_add(end, _mul(normal, r)), normal, tip,
                                       (column / sides, 2. + cap / 4)))
        rows.append(ring)
    for row in range(len(rows) - 1):
        for column in range(sides):
            builder.face(rows[row][column], rows[row][column + 1],
                         rows[row + 1][column + 1], rows[row + 1][column])
    pole = builder.vertex(_add(end, _mul(tangent, r)), tangent, tip, (.5, 3.))
    for column in range(sides):
        builder.face(rows[-1][column], rows[-1][column + 1], pole)
    for index in range(calices):
        t = .22 + .65 * (index + .5) / calices
        center, tangent = _curve(control, t)
        frame = frames[min(segments, round(t * segments))]
        u, v = frame[2:4]
        angle = phase + index * 2.399963
        radial = _add(_mul(u, math.cos(angle)), _mul(v, math.sin(angle)))
        r = radius * (1. - .24 * t)
        anchor = _add(center, _mul(radial, r * .985))
        _calice(builder, anchor, radial, tangent, radius * .19, base, health)


def _nodule(builder, center, radii, color, phase=0., rings=7, sides=12):
    """Small rounded verruca; overlaps a branch rather than floating nearby."""
    rows = []
    for row in range(rings + 1):
        theta = math.pi * row / rings
        ring = []
        for column in range(sides + 1):
            phi = math.tau * column / sides
            direction = (math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta))
            p = tuple(center[i] + direction[i] * radii[i] for i in range(3))
            normal = _unit(tuple(direction[i] / radii[i] for i in range(3)))
            tint = .92 + .08 * math.sin(phi * 3 + theta * 4 + phase) ** 2
            ring.append(builder.vertex(p, normal, _mul(color, tint), (column / sides, row / rings)))
        rows.append(ring)
    for row in range(rings):
        for column in range(sides):
            if row == 0:
                builder.face(rows[row][column], rows[row + 1][column], rows[row + 1][column + 1])
            elif row == rings - 1:
                builder.face(rows[row][column], rows[row + 1][column], rows[row][column + 1])
            else:
                builder.face(rows[row][column], rows[row + 1][column],
                             rows[row + 1][column + 1], rows[row][column + 1])


def generate_pocillopora(health, radius, height, seed):
    """Clustered blunt colony, bounded by radius and height, <30k vertices."""
    _validate(health, radius, height, seed)
    rng = random.Random(seed)
    base, tip = _palette(health, seed)
    builder = _Builder()
    _nodule(builder, (0., 0., height * .035),
            (radius * .31, radius * .29, height * .035), base, rings=7, sides=16)
    for i in range(11):
        angle = i * 2.399963 + rng.uniform(-.19, .19)
        spread = math.sqrt((i + .5) / 11)
        peak = height * rng.uniform(.68, .91)
        if i == 0:
            peak = height * .94
        if health == "dead":
            peak *= rng.uniform(.63, .84)
        root = (radius * .13 * spread * math.cos(angle), radius * .13 * spread * math.sin(angle), height * .018)
        end = (radius * .63 * spread * math.cos(angle), radius * .63 * spread * math.sin(angle), peak)
        control = (root, (root[0], root[1], height * .23),
                   (end[0] * .84, end[1] * .84, peak * .76), end)
        thickness = radius * rng.uniform(.075, .105)
        _blunt_branch(builder, control, thickness, base, tip, angle, health,
                      segments=11, sides=12, calices=12)
        for j, t in enumerate((.47, .67, .82)):
            origin, tangent = _curve(control, t)
            turn = angle + rng.choice((-1, 1)) * rng.uniform(.55, 1.6)
            reach = radius * rng.uniform(.20, .34)
            branch_end = (origin[0] + reach * math.cos(turn), origin[1] + reach * math.sin(turn),
                          min(height * .94, origin[2] + height * rng.uniform(.15, .26)))
            if health == "dead":
                branch_end = (branch_end[0], branch_end[1], origin[2] + height * .10)
            fork = (origin, _add(origin, _mul(tangent, height * .07)),
                    _mix(origin, branch_end, .70), branch_end)
            _blunt_branch(builder, fork, thickness * .65, base, tip, turn, health,
                          segments=7, sides=10, calices=7)
            # Short rounded verrucae break the otherwise smooth branch side.
            at, direction = _curve(fork, .63)
            bump = _add(at, (math.cos(turn + 1.3) * thickness * .38,
                             math.sin(turn + 1.3) * thickness * .38, thickness * .14))
            _nodule(builder, bump, (thickness * .46, thickness * .44, thickness * .63),
                    _mix(base, tip, .25), turn, rings=5, sides=8)
    mesh = builder.data
    horizontal = max(math.hypot(p[0], p[1]) for p in mesh["points"])
    highest = max(p[2] for p in mesh["points"])
    sx = radius / horizontal
    sz = height * (.79 if health == "dead" else 1.) / highest
    mesh["points"] = [(p[0] * sx, p[1] * sx, max(0., p[2] * sz)) for p in mesh["points"]]
    mesh["normals"] = [_unit((n[0] / sx, n[1] / sx, n[2] / sz)) for n in mesh["normals"]]
    return mesh


def generate_contact_fragment(seed, height=.14, radius=.025):
    """Stout upper crown, preserving every original vertex below Z=.075m.

    The entire original mesh remains in order. A smooth radial deformation
    affects only its upper crown; lower positions/normals are copied exactly.
    Added rounded verrucae and tissue-lined calices remain above Z=.075m.
    This is authored once and must never be regenerated during transfer.
    """
    _validate("healthy", radius, height, seed)
    if height < .10 or height > .25 or radius > .04:
        raise ValueError("Contact fragments require height .10–.25m and radius <=.04m")
    mesh = generate_fragment(seed, height, radius)
    max_xy = max(max(abs(p[0]), abs(p[1])) for p in mesh["points"])
    expansion = max(0., min(.95, .041 / max_xy - 1.))
    start, span = .075, height - .075

    def warp(p):
        q = max(0., min(1., (p[2] - start) / span))
        smooth = q*q * (3. - 2. * q)
        factor = 1. + expansion * smooth
        derivative = expansion * 6. * q * (1. - q) / span if start < p[2] < height else 0.
        return (p[0] * factor, p[1] * factor, p[2]), factor, derivative

    original_points, original_normals = mesh["points"][:], mesh["normals"][:]
    for i, (point, normal) in enumerate(zip(original_points, original_normals)):
        if point[2] <= .075:
            continue
        new, scale, derivative = warp(point)
        mesh["points"][i] = new
        mesh["normals"][i] = _unit((normal[0] / scale, normal[1] / scale,
                                   normal[2] - derivative * (point[0] * normal[0] + point[1] * normal[1]) / scale))
    builder = _Builder()
    builder.data = mesh
    base, tip = _palette("healthy", seed)
    curve = ((0., 0., 0.), (0., 0., height * .38),
             (radius * .12, radius * .08, height * .73), (radius * .18, radius * .12, height))
    rng = random.Random(seed)
    ends = [curve[-1]]
    crown_curves = [curve]
    for side, fraction in ((-1, .48), (1, .61)):
        origin, direction = _curve(curve, fraction)
        angle = side * .5 + rng.uniform(-.2, .2)
        end = (origin[0] + side * radius * .95, origin[1] + radius * .35 * math.sin(angle),
               height * (.84 if side < 0 else .93))
        ends.append(end)
        crown_curves.append((origin, _add(origin, _mul(direction, height * .10)),
                             _mix(origin, end, .68), end))
    for i, end in enumerate(ends):
        point, _, _ = warp(end)
        r = min(.0065, radius * .25, (point[2] - .077) * .40)
        if r <= .0005:
            continue
        center = (max(-.045+r, min(.045-r, point[0])),
                  max(-.045+r, min(.045-r, point[1])), point[2] - r)
        _nodule(builder, center, (r, r * .95, r), tip, i, rings=7, sides=12)
    # Compact side branchlets grow out of the three existing upper axes.
    # Their blunt, calice-lined ends form an irregular cauliflower crown;
    # every root intersects its parent axis and the bare grasp stem stays clear.
    for branch_index, parent in enumerate(crown_curves):
        for level, fraction in enumerate((.73, .88)):
            origin, tangent = _curve(parent, fraction)
            origin, _, _ = warp(origin)
            if origin[2] < .082 or origin[2] > height - .009:
                continue
            thickness = min(.0052, radius * .21, (height - origin[2]) * .24)
            for fork in range(2):
                angle = branch_index * 2.399963 + level * 1.3 + fork * math.pi + .25
                reach = min(.016, radius * .64)
                end = (max(-.038, min(.038, origin[0] + reach * math.cos(angle))),
                       max(-.038, min(.038, origin[1] + reach * math.sin(angle))),
                       min(height - thickness, origin[2] + .013 + .003 * fork))
                control = (origin, _add(origin, _mul(tangent, .004)),
                           _mix(origin, end, .67), end)
                _blunt_branch(builder, control, thickness, base, tip, angle, "healthy",
                              segments=6, sides=9, calices=5)
    for i in range(24):
        z = .082 + (height - .090) * (i + .5) / 24
        # Find the main-axis parameter by bisection; the Bezier Z is monotone.
        lo, hi = 0., 1.
        for _ in range(18):
            mid = (lo + hi) / 2
            p, _ = _curve(curve, mid)
            if p[2] < z:
                lo = mid
            else:
                hi = mid
        center, tangent = _curve(curve, (lo + hi) / 2)
        center, scale, _ = warp(center)
        around = i * 2.399963
        normal = (math.cos(around), math.sin(around), 0.)
        stem_r = radius * .24 * (1. - .50 * ((lo + hi) / 2)) * scale
        anchor = _add(center, _mul(normal, stem_r * .98))
        _calice(builder, anchor, normal, tangent, min(.0011, radius * .045), base, "healthy")
    return builder.data
