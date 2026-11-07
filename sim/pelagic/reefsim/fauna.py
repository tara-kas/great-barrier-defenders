"""Small reef-fish schools with replayable, history-free visual motion.

Fish are scenery, not ecosystem agents. Local +X points toward the head,
Z points up; angles are radians. Mesh dictionaries match IsaacReefScene's
``_mesh_data`` input. The tail is local to ``tail_pivot`` and rotates about Z.
No USD, network, simulation integrator or third-party dependency is needed.
"""
from __future__ import annotations

import math
import random


def _unit(vector):
    length = math.sqrt(sum(v * v for v in vector))
    return tuple(v / length for v in vector) if length > 1e-12 else (0., 0., 1.)


class _Mesh:
    def __init__(self):
        self.data = {key: [] for key in ("points", "normals", "colors", "uvs", "counts", "indices")}

    def vertex(self, point, normal, color, uv=(0., 0.)):
        index = len(self.data["points"])
        self.data["points"].append(tuple(point))
        self.data["normals"].append(_unit(normal))
        self.data["colors"].append(tuple(max(0., min(1., v)) for v in color))
        self.data["uvs"].append(tuple(uv))
        return index

    def face(self, *indices):
        self.data["counts"].append(len(indices))
        self.data["indices"].extend(indices)

    def fin(self, points, color):
        # The renderer uses double-sided meshes; flat fins stay inexpensive.
        a, b, c = points[:3]
        u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
        normal = _unit((u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]))
        self.face(*(self.vertex(point, normal, color, (index / max(1, len(points)-1), 1.))
                    for index, point in enumerate(points)))


def fish_mesh(length=.22, color=(.92, .53, .12), variant=0):
    """Return a compressed fusiform body, thin fins and a forked tail."""
    body, tail = _Mesh(), _Mesh()
    rings, sides = 12, 16
    half_x, half_y, half_z = .46 * length, .115 * length, .235 * length
    for row in range(rings + 1):
        polar = math.pi * row / rings
        x = .04 * length + half_x * math.cos(polar)
        radial = max(.015, math.sin(polar))
        for col in range(sides + 1):
            angle = math.tau * col / sides
            y, z = half_y * radial * math.cos(angle), half_z * radial * math.sin(angle)
            normal = ((x-.04*length)/(half_x*half_x), y/(half_y*half_y), z/(half_z*half_z))
            dorsal = .76 + .24 * (1. - math.sin(angle)) / 2
            # Fine longitudinal iridescent band and a pale belly.
            band = .14 if abs(math.sin(angle) + .12) < .22 else 0.
            tint = tuple(min(1., c * dorsal + band * (.4 if axis == 0 else .9)) for axis, c in enumerate(color))
            if z < -.10 * length:
                tint = tuple(c*.72 + .22 for c in tint)
            body.vertex((x, y, z), normal, tint, (col/sides, row/rings))
    for row in range(rings):
        for col in range(sides):
            a = row*(sides+1)+col
            body.face(a, a+1, a+sides+2, a+sides+1)
    fin_color = tuple(c*.76+.08 for c in color)
    scale = lambda points: [tuple(v * length for v in point) for point in points]
    body.fin(scale([(.18, 0., .16), (-.12, 0., .39), (-.34, 0., .10)]), fin_color)
    body.fin(scale([(.03, 0., -.17), (-.23, 0., -.31), (-.34, 0., -.10)]), fin_color)
    for side in (-1, 1):
        body.fin(scale([(.16, side*.10, -.03), (-.10, side*.29, -.12), (-.03, side*.085, -.07)]), fin_color)
    # Pivot is the caudal peduncle. Two lobes form a visible fork, not a box.
    tail.fin(scale([(.03, 0., .045), (-.22, 0., .26), (-.16, 0., .015), (-.03, 0., 0.)]), fin_color)
    tail.fin(scale([(-.03, 0., 0.), (-.16, 0., -.015), (-.22, 0., -.26), (.03, 0., -.045)]), fin_color)
    eyes = [{"position": [.29*length, sign*.095*length, .075*length], "radius": .024*length}
            for sign in (-1, 1)]
    return {"body_mesh": body.data, "tail_mesh": tail.data,
            "tail_pivot": [-.39*length, 0., 0.], "eyes": eyes}


def build_fauna(config, snapshot):
    """Build seeded school members once; default 42 fish in three schools.

    ``render.fish_count`` can reduce/disable the visual population (0..72).
    School centers favour the live reef and the water between coral patches.
    """
    rng = random.Random(int(config.get("seed", 26)) + 9187)
    count = max(0, min(72, int(config.get("render", {}).get("fish_count", 42))))
    world = config["world"]
    half_width, half_length = float(world["width"])/2, float(world["length"])/2
    # Reserve a whole school footprint away from the mounting workspaces.
    # Moving individual fish onto a keep-out circle compresses the formation;
    # choosing the quiet eastern quadrant keeps its rigid spacing intact.
    mounts = [coral["planting_point"] for coral in snapshot.get("corals", [])
              if coral.get("planting_point") is not None]
    east_candidates = [(.24*world["width"], .23*world["length"], 1.85),
                       (.24*world["width"], -.23*world["length"], 1.85)]
    eastern_center = max(east_candidates, key=lambda center:
                         min((math.hypot(center[0]-point[0], center[1]-point[1]) for point in mounts), default=math.inf))
    centers = [(-.25*world["width"], -.24*world["length"], 1.65),
               eastern_center,
               (-.08*world["width"], .03*world["length"], 2.30)]
    palettes = ((.95, .52, .12), (.20, .64, .82), (.62, .77, .33))
    records = []
    for index in range(count):
        school = index % len(centers)
        members = len(range(school, count, len(centers)))
        columns = math.ceil(math.sqrt(members))
        rows = math.ceil(members / columns)
        slot = index // len(centers)
        # A gently irregular lattice preserves spacing as the whole formation
        # turns. Independent random offsets could put two fish in one body.
        offset = [(slot % columns - (columns-1)/2)*.27 + rng.uniform(-.012, .012),
                  (slot // columns - (rows-1)/2)*.27 + rng.uniform(-.012, .012),
                  rng.uniform(-.18, .18)]
        length = rng.uniform(.17, .26)
        color = tuple(c*rng.uniform(.90, 1.05) for c in palettes[school])
        record = {"id": f"fish-{index+1:03d}", "school_id": school,
                  "length": length, "bounding_radius": .64*length,
                  "center": list(centers[school]), "orbit": [.80+.09*school, .54+.06*school],
                  "offset": offset,
                  "phase": school*1.8, "frequency": .18-.02*school,
                  "tail_phase": rng.uniform(0., math.tau), "tail_frequency": rng.uniform(3.3, 4.5),
                  "bounds": [half_width-.35, half_length-.35, .65, float(world["depth"])-.35]}
        record.update(fish_mesh(length, color, school))
        records.append(record)
    return records


def _constraints(record, snapshot):
    radius = record["bounding_radius"]
    cylinders = []
    for item in list(snapshot.get("corals", [])) + list(snapshot.get("obstacles", [])):
        cylinders.append((item["position"][0], item["position"][1],
                          float(item.get("radius", .3)) + radius + .14,
                          float(item["position"][2]) + float(item.get("height", .8)) + radius + .16))
    # Permanent keep-out columns prevent schools crossing the planting shot.
    for coral in snapshot.get("corals", []):
        mount = coral.get("planting_point")
        if mount is not None:
            cylinders.append((mount[0], mount[1], .68+radius, math.inf))
    spheres = [(robot["position"], .34+radius+.16) for robot in snapshot.get("robots", [])]
    return cylinders, spheres


def _safe(position, cylinders, spheres, bounds):
    x, y, z = position
    if abs(x) > bounds[0]+1e-8 or abs(y) > bounds[1]+1e-8 or not bounds[2]-1e-8 <= z <= bounds[3]+1e-8:
        return False
    if any(z < top and math.hypot(x-cx, y-cy) < radius-1e-7 for cx, cy, radius, top in cylinders):
        return False
    return not any(sum((position[i]-center[i])**2 for i in range(3)) < radius*radius-1e-7
                   for center, radius in spheres)


def _avoid(position, record, snapshot):
    cylinders, spheres = _constraints(record, snapshot)
    bounds = record["bounds"]
    result = list(position)
    # Anticipate reef relief with a smooth height field instead of teleporting
    # upward at a colony's edge. The subsequent projection is a safety guard.
    for cx, cy, radius, top in cylinders:
        if not math.isfinite(top) or top+.04 >= bounds[3]:
            continue
        distance = math.hypot(result[0]-cx, result[1]-cy)
        blend = max(0., min(1., (radius+.50-distance)/.50))
        blend = blend*blend*(3.-2.*blend)
        result[2] = max(result[2], position[2]+max(0., top+.04-position[2])*blend)
    # Pass above vehicles using a broad, continuously varying height field.
    # Projecting radially away from a sphere becomes arbitrarily fast when a
    # nominal path crosses its centerline; this chooses one stable passing side.
    for center, radius in spheres:
        top = center[2]+radius+.05
        if top >= bounds[3]:
            continue
        distance = math.hypot(result[0]-center[0], result[1]-center[1])
        blend = max(0., min(1., (radius+.85-distance)/.85))
        blend = blend*blend*(3.-2.*blend)
        result[2] = max(result[2], position[2]+max(0., top-position[2])*blend)
    for _ in range(16):
        result[0] = max(-bounds[0], min(bounds[0], result[0]))
        result[1] = max(-bounds[1], min(bounds[1], result[1]))
        result[2] = max(bounds[2], min(bounds[3], result[2]))
        for cx, cy, radius, top in cylinders:
            dx, dy = result[0]-cx, result[1]-cy
            distance = math.hypot(dx, dy)
            if result[2] < top and distance < radius:
                # Rise above ordinary colonies where possible; worksite columns
                # remain an absolute horizontal exclusion at every altitude.
                if math.isfinite(top) and top+.04 < bounds[3]:
                    result[2] = top+.04
                else:
                    direction = (dx/distance, dy/distance) if distance > 1e-9 else (1., 0.)
                    result[0], result[1] = cx+direction[0]*(radius+.025), cy+direction[1]*(radius+.025)
        for center, radius in spheres:
            delta = [result[i]-center[i] for i in range(3)]
            distance = math.sqrt(sum(v*v for v in delta))
            if distance < radius:
                direction = [v/distance for v in delta] if distance > 1e-9 else [0., 0., 1.]
                result = [center[i]+direction[i]*(radius+.025) for i in range(3)]
        if _safe(result, cylinders, spheres, bounds):
            return result
    # Rare crowded/boundary cases choose the nearest deterministic safe sample.
    # This is evaluated from this snapshot alone; calling order never matters.
    candidates = []
    for layer in (min(bounds[3], max(position[2], 2.6)), bounds[3]):
        for row in range(13):
            for col in range(13):
                candidate = [-bounds[0]+2*bounds[0]*col/12, -bounds[1]+2*bounds[1]*row/12, layer]
                if _safe(candidate, cylinders, spheres, bounds):
                    candidates.append(candidate)
    if not candidates:
        raise ValueError("No safe visual fish position in this bounded reef layout")
    return min(candidates, key=lambda candidate: sum((candidate[i]-position[i])**2 for i in range(3)))


def fauna_pose(record, time, snapshot):
    """Return safe position, heading and tail oscillation for an absolute time.

    Members share an ellipse and speed, retaining seeded school-relative
    offsets. Avoidance is visual geometry exclusion rather than fish physics.
    """
    time = float(time)
    if not math.isfinite(time):
        raise ValueError("Fish replay time must be finite")
    phase = record["phase"] + time*record["frequency"]
    c, s = math.cos(phase), math.sin(phase)
    ox, oy, oz = record["offset"]
    rx, ry = record["orbit"]
    center = record["center"]
    position = [center[0]+rx*c+ox*c-oy*s,
                center[1]+ry*s+ox*s+oy*c,
                center[2]+oz+.10*math.sin(phase*1.7+record["tail_phase"]*.2)]
    yaw = math.atan2(ry*c+ox*c-oy*s, -rx*s-ox*s-oy*c)
    tail_angle = .24*math.sin(time*math.tau*record["tail_frequency"]+record["tail_phase"])
    return {"position": _avoid(position, record, snapshot), "yaw": yaw, "tail_angle": tail_angle}
