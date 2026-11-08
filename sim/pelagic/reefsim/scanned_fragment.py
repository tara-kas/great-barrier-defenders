"""Persistent cuttings split from the bundled, UV-mapped Pocillopora scan.

This is geometric branch harvesting, not a biological fracture model. Small
connected terminal clusters are separated along existing triangle edges. The
paired cut surfaces expose a pale skeleton; no trunk, roots, or new branch is
generated. Source provenance is assets/pocillopora/manifest.json (CC0).

Runtime requires only Python's standard library. Selection/topology are cached;
returned mesh buffers are independent and can safely be edited by a renderer.
"""
from functools import lru_cache
import math

from .pocillopora_scan import _load, generate_pocillopora_scan


@lru_cache(maxsize=2)
def _topology(detail):
    source = _load(detail)
    ratio = source["source_height"] / source["source_radius"]
    points = [tuple(p[:2]) + (p[2] * ratio,) for p in source["points"]]
    faces = tuple(zip(*[iter(source["indices"])] * 3))
    welded, vertex_ids = {}, []
    for point in points:
        key = tuple(round(v, 7) for v in point)
        vertex_ids.append(welded.setdefault(key, len(welded)))
    edge_faces, neighbours = {}, [[] for _ in faces]
    for index, face in enumerate(faces):
        a, b, c = [vertex_ids[v] for v in face]
        for x, y in ((a, b), (b, c), (c, a)):
            edge = (min(x, y), max(x, y))
            for other in edge_faces.get(edge, ()):
                neighbours[index].append(other)
                neighbours[other].append(index)
            edge_faces.setdefault(edge, []).append(index)
    centers = [tuple(sum(points[v][k] for v in face) / 3 for k in range(3))
               for face in faces]
    return points, faces, tuple(tuple(n) for n in neighbours), centers, tuple(vertex_ids)


@lru_cache(maxsize=2)
def _selections(detail):
    points, faces, neighbours, centers, _ = _topology(detail)
    height = max(p[2] for p in points)
    candidates = []
    # Search elevations rather than hard-coded vertex numbers. UV seam vertices
    # are welded for connectivity ONLY; source attributes remain untouched.
    for percent in range(50, 87, 2):
        unseen = {i for i, p in enumerate(centers) if p[2] > height * percent / 100}
        while unseen:
            first = min(unseen)
            unseen.remove(first)
            component, pending = {first}, [first]
            while pending:
                for adjacent in neighbours[pending.pop()]:
                    if adjacent in unseen:
                        unseen.remove(adjacent)
                        component.add(adjacent)
                        pending.append(adjacent)
            if not max(25, len(faces) * .001) < len(component) < len(faces) * .08:
                continue
            vertices = {v for i in component for v in faces[i]}
            low = [min(points[v][k] for v in vertices) for k in range(3)]
            high = [max(points[v][k] for v in vertices) for k in range(3)]
            width, branch_height = max(high[k] - low[k] for k in (0, 1)), high[2] - low[2]
            if not .12 * height < branch_height < .34 * height or width > .43 * height:
                continue
            center = tuple((a + b) / 2 for a, b in zip(low, high))
            score = branch_height / width + .6 * branch_height / height + .2 * math.hypot(*center[:2]) / height
            candidates.append((score, first, frozenset(component), center))
    chosen = []
    for candidate in sorted(candidates, key=lambda c: (-c[0], c[1])):
        if any(candidate[2] & prior[2] or math.dist(candidate[3], prior[3]) < .2 * height
               for prior in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) == 2:
            break
    if len(chosen) != 2:
        raise ValueError("The bundled scan does not contain two suitable terminal branch clusters")
    return tuple(tuple(sorted(item[2])) for item in chosen)


def _subset(mesh, faces, selected, origin=(0., 0., 0.)):
    selected = tuple(sorted(selected))
    vertex_ids = sorted({v for index in selected for v in faces[index]})
    remap = {old: new for new, old in enumerate(vertex_ids)}
    result = {key: [tuple(mesh[key][v]) for v in vertex_ids]
              for key in ("normals", "colors", "uvs")}
    result["points"] = [tuple(mesh["points"][v][k] - origin[k] for k in range(3)) for v in vertex_ids]
    result["indices"] = [remap[v] for i in selected for v in faces[i]]
    result["counts"] = [3] * len(selected)
    result["source_triangle_indices"] = list(selected)
    result["source_vertex_indices"] = vertex_ids
    result["source_triangle_count"] = len(selected)
    return result


def _boundary_edges(faces, selected, vertex_ids):
    edges = {}
    for index in selected:
        a, b, c = faces[index]
        for x, y in ((a, b), (b, c), (c, a)):
            key = tuple(sorted((vertex_ids[x], vertex_ids[y])))
            if key in edges:
                edges.pop(key)
            else:
                edges[key] = (x, y)
    return list(edges.values())


def _cap(mesh, source, edges, origin, reverse=False):
    """Cap each boundary loop separately, preserving the small ragged cut edge."""
    by_position = {}
    for a, b in edges:
        for v in (a, b):
            by_position.setdefault(tuple(round(x, 7) for x in source["points"][v]), v)
    # The harvested component can have several narrow attachments. Never fan
    # disconnected loops to one center, which would bridge empty seawater.
    vertex_neighbors = {}
    keyed_edges = []
    for a, b in edges:
        ka, kb = [tuple(round(x, 7) for x in source["points"][v]) for v in (a, b)]
        vertex_neighbors.setdefault(ka, set()).add(kb)
        vertex_neighbors.setdefault(kb, set()).add(ka)
        keyed_edges.append((ka, kb, a, b))
    unseen = set(vertex_neighbors)
    count = 0
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        component, pending = {start}, [start]
        while pending:
            for key in vertex_neighbors[pending.pop()]:
                if key in unseen:
                    unseen.remove(key)
                    component.add(key)
                    pending.append(key)
        loop = [(a, b) for ka, kb, a, b in keyed_edges if ka in component]
        ids = [by_position[key] for key in sorted(component)]
        center = tuple(sum(source["points"][v][k] for v in ids) / len(ids) for k in range(3))
        uv = tuple(sum(source["uvs"][v][k] for v in ids) / len(ids) for k in range(2))
        for a, b in loop:
            # Source boundary is oriented with the tissue; cap reverses it.
            triangle = [source["points"][b], source["points"][a], center]
            if reverse:
                triangle.reverse()
            u = [triangle[1][k] - triangle[0][k] for k in range(3)]
            v = [triangle[2][k] - triangle[0][k] for k in range(3)]
            normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            size = math.hypot(*normal)
            if size < 1e-14:
                continue
            first = len(mesh["points"])
            mesh["points"].extend(tuple(p[k]-origin[k] for k in range(3)) for p in triangle)
            mesh["normals"].extend([tuple(n/size for n in normal)] * 3)
            mesh["colors"].extend([(.68, .63, .49)] * 3)
            mesh["uvs"].extend([uv] * 3)
            mesh["indices"].extend((first, first+1, first+2))
            mesh["counts"].append(3)
            count += 1
    return count


def split_scanned_donor(radius, height, seed=0, slots=2, *, detail="hero", cap=True):
    """Return an intact donor represented by parent + removable real branches.

    Each fragment ``mesh`` uses Z=0 at its lowest scanned vertex. Adding its
    ``origin`` reconstructs the original donor-local geometry exactly, with
    **zero initial yaw**. The parent uses unchanged donor coordinates. A caller
    assigns its persistent mission fragment ID to the selected ``slot`` and
    moves this same mesh thereafter. Generate with the same seed/detail as the
    original colony. No stretching, clipping, or UV remapping is performed.

    ``grasp_point`` is the center of the lower natural branch cross-section;
    ``grasp_radius`` is its conservative radial extent. ``contact_samples`` are
    real surface points around that lower section, suitable for solving a
    recipient contact pose instead of assuming a synthetic cylindrical stem.
    """
    if isinstance(slots, bool) or not isinstance(slots, int) or not 0 <= slots <= 2:
        raise ValueError("slots must be 0, 1, or 2")
    source = generate_pocillopora_scan("healthy", radius, height, seed, detail=detail)
    _, faces, _, _, vertex_ids = _topology(detail)
    selections = _selections(detail)[:slots]
    removed = set().union(*map(set, selections)) if selections else set()
    parent = _subset(source, faces, set(range(len(faces))) - removed)
    fragments = []
    for slot, selected in enumerate(selections):
        vertices = sorted({v for index in selected for v in faces[index]})
        pts = [source["points"][v] for v in vertices]
        low, high = min(p[2] for p in pts), max(p[2] for p in pts)
        branch_height = high - low
        band = [p for p in pts if .20 * branch_height <= p[2]-low <= .38 * branch_height]
        if not band:
            raise ValueError("Selected branch has no grasp cross-section")
        cx = (min(p[0] for p in band)+max(p[0] for p in band))/2
        cy = (min(p[1] for p in band)+max(p[1] for p in band))/2
        origin = (cx, cy, low)
        mesh = _subset(source, faces, selected, origin)
        source_points = mesh["points"][:]
        edges = _boundary_edges(faces, selected, vertex_ids)
        cap_count = _cap(mesh, source, edges, origin) if cap else 0
        if cap:
            _cap(parent, source, edges, (0., 0., 0.), reverse=True)
        # Bound the full original branch, not just the grasp band.
        branch_radius = max(math.hypot(p[0], p[1]) for p in source_points)
        contact = [tuple(p[k]-origin[k] for k in range(3)) for p in band]
        stride = max(1, len(contact)//96)
        fragments.append({"slot": slot, "mesh": mesh, "origin": origin, "yaw": 0.,
                          "height": branch_height, "radius": branch_radius,
                          "grasp_point": (0., 0., branch_height*.29),
                          "grasp_z": branch_height*.29,
                          "grasp_radius": max(math.hypot(p[0]-cx, p[1]-cy) for p in band),
                          "contact_band_local_z": (branch_height*.20, branch_height*.38),
                          "contact_samples": contact[::stride],
                          "source_triangle_indices": list(selected),
                          "source_triangle_count": len(selected), "cap_triangle_count": cap_count})
    return {"parent": parent, "fragments": fragments,
            "source_triangle_count": len(faces), "source_vertex_count": len(source["points"]),
            "detail": detail, "seed": seed,
            "method": "connected terminal scan triangles; shared cut seam; no generated living geometry"}
