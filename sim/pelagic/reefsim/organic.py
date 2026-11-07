"""Seeded, smooth coral geometry independent of USD or a rendering runtime.

The meshes are visual approximations of branching and massive coral growth,
not species-identification models. Dimensions are metres and Z is up. All
vertices carry smooth normals, UVs and pigment colour so a renderer can add
fine PBR detail without the faceting of the original demo primitives.
"""
from __future__ import annotations

import math
import random


def _add(a, b):
    return tuple(a[i] + b[i] for i in range(3))


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _mul(a, s):
    return tuple(v * s for v in a)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v, fallback=(0., 0., 1.)):
    size = math.sqrt(_dot(v, v))
    return _mul(v, 1 / size) if size > 1e-12 else fallback


def _mix(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def _curve(points, t):
    """Cubic Bezier position and derivative."""
    a, b, c, d = points
    q = 1 - t
    position = tuple(q ** 3 * a[i] + 3 * q * q * t * b[i] + 3 * q * t * t * c[i] + t ** 3 * d[i] for i in range(3))
    tangent = tuple(3 * q * q * (b[i] - a[i]) + 6 * q * t * (c[i] - b[i]) + 3 * t * t * (d[i] - c[i]) for i in range(3))
    return position, _unit(tangent)


class _Builder:
    def __init__(self):
        self.data = {key: [] for key in ("points", "normals", "colors", "uvs", "counts", "indices")}

    def vertex(self, point, normal, color, uv):
        index = len(self.data["points"])
        self.data["points"].append(tuple(point))
        self.data["normals"].append(_unit(normal))
        self.data["colors"].append(tuple(max(0., min(1., v)) for v in color))
        self.data["uvs"].append(tuple(uv))
        return index

    def face(self, *indices):
        self.data["counts"].append(len(indices))
        self.data["indices"].extend(indices)

    def curved_tube(self, control, radius, color, tip_color, phase, polyp=True, segments=11, sides=12):
        """Parallel-transport frames make curved branches smooth and untwisted."""
        previous_u = None
        rings = []
        frames = []
        # A final tapered shoulder followed by a rounded terminal cap.
        for row in range(segments + 1):
            t = row / (segments + 1)
            center, tangent = _curve(control, t)
            if previous_u is None:
                reference = (1., 0., 0.) if abs(tangent[2]) > .8 else (0., 0., 1.)
                u = _unit(_cross(tangent, reference))
            else:
                u = _unit(_sub(previous_u, _mul(tangent, _dot(previous_u, tangent))))
            v = _unit(_cross(tangent, u))
            previous_u = u
            taper = 1. - .50 * t
            # The organic surface relief stays below a millimetre on typical stems.
            radial_size = radius * taper
            if t > .83:
                radial_size *= math.sqrt(max(.08, 1. - ((t - .83) / .17) ** 2))
            color_t = max(0., min(1., (t - .72) / .28))
            ring_color = _mix(color, tip_color, color_t * color_t)
            ring = []
            for col in range(sides + 1):
                angle = math.tau * col / sides
                radial = _add(_mul(u, math.cos(angle)), _mul(v, math.sin(angle)))
                texture = 1. + .035 * math.sin(angle * 5 + t * 13 + phase)
                point = _add(center, _mul(radial, radial_size * texture))
                # A small axial component gives taper a smooth physically plausible normal.
                normal = _unit(_add(radial, _mul(tangent, .11 + max(0., t - .82) * 5.)))
                tint = .97 + .03 * math.sin(angle * 3 + phase + t * 8)
                ring.append(self.vertex(point, normal, _mul(ring_color, tint), (col / sides, t * 3.)))
            rings.append(ring)
            frames.append((center, tangent, u, v, radial_size))
        for row in range(len(rings) - 1):
            for col in range(sides):
                self.face(rings[row][col], rings[row][col + 1], rings[row + 1][col + 1], rings[row + 1][col])
        tip, tangent = _curve(control, 1.)
        terminal = self.vertex(tip, tangent, tip_color, (.5, 3.))
        for col in range(sides):
            self.face(rings[-1][col], rings[-1][col + 1], terminal)
        # Exposed calices are small cups embedded in the skeleton, not long spikes.
        if polyp:
            for row, angular in ((3, phase), (6, phase + 2.3), (9, phase + 4.6)):
                center, tangent, u, v, stem_radius = frames[min(row, len(frames) - 1)]
                normal = _add(_mul(u, math.cos(angular)), _mul(v, math.sin(angular)))
                anchor = _add(center, _mul(normal, stem_radius * .94))
                self.calice(anchor, normal, tangent, max(.0008, radius * .17), color)

    def calice(self, anchor, normal, tangent, radius, color):
        u = _unit(_cross(normal, tangent))
        v = _unit(_cross(normal, u))
        rows = []
        for row, (height, ring_radius) in enumerate(((0., radius), (radius * .85, radius * .78), (radius * .65, radius * .42))):
            center = _add(anchor, _mul(normal, height))
            ring = []
            for col in range(7):
                angle = col * math.tau / 6
                radial = _add(_mul(u, math.cos(angle)), _mul(v, math.sin(angle)))
                n = _unit(_add(_mul(radial, 1 if row < 2 else -.5), _mul(normal, .7)))
                tint = _mix(color, (.68, .65, .52), .22 if row == 1 else .03)
                ring.append(self.vertex(_add(center, _mul(radial, ring_radius)), n, tint, (col / 6, row / 2)))
            rows.append(ring)
        for row in range(2):
            for col in range(6):
                self.face(rows[row][col], rows[row][col + 1], rows[row + 1][col + 1], rows[row + 1][col])
        center = self.vertex(_add(anchor, _mul(normal, radius * .37)), normal, _mul(color, .53), (.5, .5))
        for col in range(6):
            self.face(rows[-1][col], rows[-1][col + 1], center)


def _pigment(health, seed):
    if health == "bleached_alive":
        return (.76, .73, .62), (.86, .83, .73)
    if health == "dead":
        return (.23, .28, .18), (.29, .32, .22)
    # Tissue pigmentation remains visible under blue-green water illumination;
    # warm ochre, coral orange, muted violet and blue-green are non-emissive.
    palette = ((.62, .29, .16), (.60, .44, .18), (.46, .27, .58), (.20, .48, .36), (.62, .27, .23))
    base = palette[seed % len(palette)]
    return base, _mix(base, (.78, .74, .61), .72)


def _branching(builder, radius, height, seed, health, low=False):
    """Irregular arborescent/corymbose thickets, never radial tree spokes."""
    rng = random.Random(seed)
    base_color, tip_color = _pigment(health, seed)
    dead = health == "dead"
    corymbose = seed % 3 == 0
    # A broad encrusting foot connects the stems into one reef colony.
    _boulder(builder, radius * .73, height * .045, seed + 47, health, brain=False, low=low)
    count = (11 if corymbose else 9) if low else (16 if corymbose else 13)
    if dead:
        count = max(6, int(count * .72))
    stem_radius = max(.0038, radius * (.046 if corymbose else .055))
    for branch in range(count):
        # Golden-angle packing is jittered and offset so colony centres are
        # dense and irregular, rather than an evenly spaced radial fan.
        angle = branch * 2.399963 + rng.uniform(-.28, .28)
        packing = math.sqrt((branch + .35) / count)
        root_radius = radius * packing * .56
        root = (root_radius * math.cos(angle), root_radius * math.sin(angle), height * .018)
        lean = radius * rng.uniform(.11, .29)
        lean_angle = angle + rng.uniform(-.8, .8)
        peak = height if branch == 0 else height * rng.uniform(.73 if corymbose else .60, .98)
        if dead:
            # Storm/erosion losses leave unequal blunt ends and broken crowns.
            peak *= rng.uniform(.45, .78)
        end = (root[0] + lean * math.cos(lean_angle), root[1] + lean * math.sin(lean_angle), peak)
        control = (root,
                   (root[0] - lean * .15 * math.sin(angle), root[1] + lean * .15 * math.cos(angle), peak * .32),
                   (end[0] - lean * .22 * math.cos(angle + .5), end[1] - lean * .22 * math.sin(angle + .5), peak * .71), end)
        stem_color = _mul(base_color, rng.uniform(.88, 1.12))
        grown_tip = _mix(stem_color, tip_color, .18) if dead else tip_color
        builder.curved_tube(control, stem_radius * rng.uniform(.82, 1.13), stem_color, grown_tip, angle,
                            polyp=not low and not dead, segments=6 if low else 10, sides=7 if low else 11)
        fork_count = 2 if low else 3
        for fork in range(fork_count):
            origin_t = (.43, .65, .79)[fork] + rng.uniform(-.035, .035)
            origin, direction = _curve(control, origin_t)
            turn = rng.uniform(-math.pi, math.pi)
            reach = radius * rng.uniform(.21, .42)
            branch_peak = min(height * .995, origin[2] + height * rng.uniform(.19, .31))
            if dead:
                branch_peak = min(peak * 1.10, origin[2] + height * rng.uniform(.08, .16))
                reach *= rng.uniform(.8, 1.25)
            target = (origin[0] + reach * math.cos(turn), origin[1] + reach * math.sin(turn), branch_peak)
            sub = (origin, _add(origin, _mul(direction, height * .095)),
                   (target[0] - reach * .24 * math.cos(turn), target[1] - reach * .24 * math.sin(turn),
                    origin[2] + (target[2] - origin[2]) * .54), target)
            builder.curved_tube(sub, stem_radius * .56, stem_color, grown_tip, turn,
                                polyp=not low and not dead, segments=5 if low else 8, sides=6 if low else 9)
            if low or (dead and rng.random() < .45):
                continue
            twig_start, twig_direction = _curve(sub, .64)
            twig_angle = turn + rng.choice((-1, 1)) * rng.uniform(.7, 1.4)
            twig_reach = radius * rng.uniform(.09, .19)
            twig_end = (twig_start[0] + twig_reach * math.cos(twig_angle),
                        twig_start[1] + twig_reach * math.sin(twig_angle),
                        min(height, twig_start[2] + height * rng.uniform(.08, .15)))
            twig = (twig_start, _add(twig_start, _mul(twig_direction, height * .05)),
                    _mix(twig_start, twig_end, .6), twig_end)
            builder.curved_tube(twig, stem_radius * .31, stem_color, grown_tip, twig_angle,
                                polyp=False, segments=6, sides=8)


def _boulder(builder, radius, height, seed, health, brain=True, low=False):
    rng = random.Random(seed)
    phase = rng.uniform(0., math.tau)
    color, _ = _pigment(health, seed)
    sectors, rings = ((32, 16) if brain else (20, 6)) if low else ((240, 120) if brain else (40, 12))

    def surface(theta, phi):
        s, c = math.sin(theta), math.cos(theta)
        x, y = s * math.cos(phi), s * math.sin(phi)
        lobes = 1. + .075 * math.sin(phi * 3 + phase) * s ** 2 + .045 * math.sin(phi * 5 - theta * 2 + phase) * s
        # Smooth, shallow, meandering skeletal walls rather than jagged bumps.
        field = math.sin(17 * x + 1.7 * math.sin(8 * y + phase) + 1.1 * math.sin(5 * c))
        field += .63 * math.sin(18 * y + 1.3 * math.sin(7 * c + phase))
        ridge = math.exp(-((field - .12) / .28) ** 2) if brain else 0.
        relief = ((.010 if low else .018) * ridge - .003) * (s * .5 + .5) if brain else 0.
        if health == "dead" and brain:
            pits = math.exp(-((math.sin(phi * 9 + theta * 6 + phase) + .55 * math.sin(theta * 11 - phi * 3)) / .23) ** 2)
            relief -= .022 * pits * s
        rr = radius * lobes + height * relief
        z = max(0., height * c * (1. + .035 * math.sin(phi * 4 + phase) * s * s) + height * relief * c)
        return (rr * x, rr * y, z), ridge

    top, _ = surface(0., 0.)
    pole = builder.vertex(top, (0., 0., 1.), _mul(color, 1.02), (.5, 0.))
    rows = []
    epsilon = 1e-4
    for row in range(1, rings + 1):
        theta = row / rings * math.pi / 2
        ring = []
        for col in range(sectors + 1):
            phi = col / sectors * math.tau
            point, ridge = surface(theta, phi)
            a, _ = surface(max(0., theta - epsilon), phi)
            b, _ = surface(min(math.pi / 2, theta + epsilon), phi)
            c, _ = surface(theta, phi - epsilon)
            d, _ = surface(theta, phi + epsilon)
            normal = _unit(_cross(_sub(b, a), _sub(d, c)))
            pigment = .80 + ridge * .27 + .035 * math.sin(phi * 7 + theta * 11 + phase)
            # Encrusting algae are mottled, never fluorescent signal colours.
            vertex_color = _mul(color, pigment)
            if health == "dead":
                algae = .5 + .5 * math.sin(phi * 11 + 2 * math.sin(theta * 7))
                vertex_color = _mix(vertex_color, (.18, .26, .11), algae * .22)
            ring.append(builder.vertex(point, normal, vertex_color, (col / sectors * 2., row / rings)))
        rows.append(ring)
    for col in range(sectors):
        builder.face(pole, rows[0][col], rows[0][col + 1])
    for row in range(len(rows) - 1):
        for col in range(sectors):
            builder.face(rows[row][col], rows[row + 1][col], rows[row + 1][col + 1], rows[row][col + 1])


def _plating(builder, radius, height, seed, health, low=False):
    """Layered tabular plates with scalloped margins and a short supporting stem."""
    rng = random.Random(seed)
    color, tip_color = _pigment(health, seed)
    builder.curved_tube(((0, 0, 0), (.01, 0, height * .25), (-.01, .01, height * .5),
                         (0, 0, height * .82)), max(.008, radius * .045), color, color,
                        seed % 7, polyp=False, segments=6, sides=8)
    sectors, rings = (32, 7) if low else (64, 12)
    tiers = 3 if health != "dead" else 2
    for tier in range(tiers):
        phase = rng.uniform(0, math.tau)
        width = radius * (.60 + .18 * tier) * rng.uniform(.90, 1.07)
        level = height * (.34 + .25 * tier)
        offset = (rng.uniform(-.14, .14) * radius, rng.uniform(-.14, .14) * radius)
        def surface(t, phi, bottom=False):
            scallop = 1 + .11 * math.sin(phi * 3 + phase) + .065 * math.sin(phi * 7 + phase) + .02 * math.sin(phi * 13 - phase)
            r = width * t * scallop
            z = level + height * (.10 * t * t + .025 * math.sin(phi * 5 + phase) * t * t)
            z -= max(.004, height * .045) if bottom else 0
            return (offset[0] + r * math.cos(phi), offset[1] + r * math.sin(phi), z)
        for bottom in (False, True):
            rows = []
            center = builder.vertex(surface(0, 0, bottom), (0, 0, -1 if bottom else 1),
                                    _mul(color, .70 if bottom else .90), (.5, .5))
            for row in range(1, rings + 1):
                t = row / rings
                ring = []
                for col in range(sectors + 1):
                    phi = math.tau * col / sectors
                    point = surface(t, phi, bottom)
                    a = surface(max(0., t - .001), phi, bottom)
                    b = surface(min(1., t + .001), phi, bottom)
                    c = surface(t, phi - .001, bottom)
                    d = surface(t, phi + .001, bottom)
                    normal = _unit(_cross(_sub(b, a), _sub(d, c)))
                    if bottom:
                        normal = _mul(normal, -1)
                    rim = max(0., (t - .88) / .12)
                    pigment = _mix(color, tip_color, rim * .55)
                    if bottom:
                        pigment = _mul(pigment, .65)
                    ring.append(builder.vertex(point, normal, pigment,
                                               (.5 + point[0] / .16, .5 + point[1] / .16)))
                rows.append(ring)
            for col in range(sectors):
                if health == "dead" and math.sin(col * math.tau / sectors * 3 + phase) > .72:
                    continue
                ids = (center, rows[0][col], rows[0][col + 1])
                builder.face(*(reversed(ids) if bottom else ids))
            for row in range(rings - 1):
                for col in range(sectors):
                    if health == "dead" and row > rings * .45 and math.sin(col * math.tau / sectors * 3 + phase) > .72:
                        continue
                    ids = (rows[row][col], rows[row + 1][col], rows[row + 1][col + 1], rows[row][col + 1])
                    builder.face(*(reversed(ids) if bottom else ids))


def generate_fragment(seed: int, height: float = .16, radius: float = .025) -> dict:
    """A single detachable Y-shaped cutting with a clean bare grasp stem.

    The local origin is the cut end. The lower four centimetres are a single
    stem, with no encrusting mound, substrate plug, radial roots or hidden
    colony geometry. Keep one mesh instance for donor, carry and placement.
    The nominal pinch centre is at local Z=.045 m; stem diameter is 0.48×radius.
    """
    if not math.isfinite(height) or not math.isfinite(radius) or height < .08 or radius <= 0:
        raise ValueError("Fragment height must be at least .08m and radius positive")
    rng = random.Random(seed)
    color, tip_color = _pigment("healthy", seed)
    builder = _Builder()
    stem_radius = radius * .24
    curve = ((0., 0., 0.), (0., 0., height * .38),
             (radius * .12, radius * .08, height * .73),
             (radius * .18, radius * .12, height))
    builder.curved_tube(curve, stem_radius, color, tip_color, .3,
                        polyp=False, segments=17, sides=14)
    # A flat cut face closes the sole stem; it does not flare into a base.
    centre = builder.vertex((0, 0, 0), (0, 0, -1), _mix(color, (.77, .72, .58), .50), (.5, .5))
    cut = [builder.vertex(builder.data["points"][i], (0, 0, -1),
                          _mix(color, (.77, .72, .58), .50), (.5, .5)) for i in range(15)]
    for i in range(14):
        builder.face(centre, cut[i + 1], cut[i])
    for side, fraction in ((-1, .48), (1, .61)):
        start, direction = _curve(curve, fraction)
        angle = side * .5 + rng.uniform(-.2, .2)
        end = (start[0] + side * radius * .95, start[1] + radius * .35 * math.sin(angle),
               height * (.84 if side < 0 else .93))
        control = (start, _add(start, _mul(direction, height * .10)), _mix(start, end, .68), end)
        builder.curved_tube(control, stem_radius * .63, color, tip_color, side + .4,
                            polyp=True, segments=9, sides=10)
    return builder.data


def generate_coral(morphology: str, health: str, radius: float, height: float, seed: int, *, detail="full") -> dict:
    """Return indexed smooth geometry with matching point attributes.

    ``branching`` creates a branching colony with rounded growing tips and
    small skeletal calices; ``boulder`` creates a lobed brain-coral dome.
    UVs are suitable for repeating fine tissue normal/roughness maps. The
    maximum branch extent can modestly exceed ``radius`` at secondary tips;
    ``radius`` is a colony scale rather than a guaranteed bounding sphere.
    """
    if morphology not in ("branching", "boulder", "plating", "tabular"):
        raise ValueError("morphology must be branching, boulder or plating")
    if detail not in ("full", "low"):
        raise ValueError("detail must be full or low")
    if health not in ("healthy", "bleached_alive", "dead"):
        raise ValueError("health must be healthy, bleached_alive or dead")
    if not math.isfinite(radius) or not math.isfinite(height) or radius <= 0 or height <= 0:
        raise ValueError("radius and height must be finite positive dimensions")
    builder = _Builder()
    if morphology == "branching":
        _branching(builder, float(radius), float(height), int(seed), health, low=detail == "low")
    elif morphology in ("plating", "tabular"):
        _plating(builder, float(radius), float(height), int(seed), health, low=detail == "low")
    else:
        _boulder(builder, float(radius), float(height), int(seed), health, low=detail == "low")
    return builder.data
