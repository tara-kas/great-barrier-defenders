"""Contact planning on the existing Smithsonian colony surface.

No recipient tissue is invented here. Candidate points lie on triangles of
the same indexed mesh consumed by the renderer. Geometry queries are a
kinematic clearance approximation, not tissue mechanics or force closure.
"""
from __future__ import annotations

import math
from functools import lru_cache

from .pocillopora_scan import generate_pocillopora_scan


def _add(a, b):
    return tuple(a[i] + b[i] for i in range(3))


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _mul(a, scale):
    return tuple(x * scale for x in a)


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def closest_point_on_triangle(point, a, b, c):
    """Closest point including triangle edges/vertices (Ericson regions)."""
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(point, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return tuple(a)
    bp = _sub(point, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return tuple(b)
    vc = d1*d4 - d3*d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return _add(a, _mul(ab, d1 / (d1-d3)))
    cp = _sub(point, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return tuple(c)
    vb = d5*d2 - d1*d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return _add(a, _mul(ac, d2 / (d2-d6)))
    va = d3*d6 - d5*d4
    if va <= 0 and d4-d3 >= 0 and d5-d6 >= 0:
        return _add(b, _mul(_sub(c,b), (d4-d3) / ((d4-d3)+(d5-d6))))
    denominator = va+vb+vc
    if abs(denominator) < 1e-24:
        return min((tuple(a),tuple(b),tuple(c)), key=lambda p: _dot(_sub(point,p),_sub(point,p)))
    return _add(a, _add(_mul(ab,vb/denominator),_mul(ac,vc/denominator)))


class SurfaceQuery:
    """Small spatial index for independent queries against actual triangles.

    ``signed_distance`` uses the outward winding of the nearest triangle.
    It is a local surface separation, not a general-purpose watertight SDF.
    """
    def __init__(self, points, indices, cell_size=.025):
        if len(indices) % 3:
            raise ValueError("SurfaceQuery requires triangles")
        self.points = [tuple(float(v) for v in p) for p in points]
        self.indices = list(indices)
        self.cell_size = cell_size
        self.triangles = []
        self.bounds = []
        self.grid = {}
        for index in range(0,len(indices),3):
            triangle = tuple(self.points[indices[index+j]] for j in range(3))
            normal = _cross(_sub(triangle[1],triangle[0]),_sub(triangle[2],triangle[0]))
            length = math.hypot(*normal)
            unit = _mul(normal,1/length) if length > 1e-15 else (0.,0.,1.)
            self.triangles.append((triangle,unit))
            box = tuple((min(p[k] for p in triangle), max(p[k] for p in triangle)) for k in range(3))
            self.bounds.append(box)
            bounds = [(math.floor(low/cell_size), math.floor(high/cell_size)) for low,high in box]
            for x in range(bounds[0][0],bounds[0][1]+1):
                for y in range(bounds[1][0],bounds[1][1]+1):
                    for z in range(bounds[2][0],bounds[2][1]+1):
                        self.grid.setdefault((x,y,z),set()).add(index//3)

    def nearby_triangles(self, point, radius):
        bounds=[(math.floor((v-radius)/self.cell_size),math.floor((v+radius)/self.cell_size)) for v in point]
        result=set()
        for x in range(bounds[0][0],bounds[0][1]+1):
            for y in range(bounds[1][0],bounds[1][1]+1):
                for z in range(bounds[2][0],bounds[2][1]+1):
                    result.update(self.grid.get((x,y,z),()))
        return sorted(result)

    def nearest(self, point, radius=.04):
        best = None
        for index in self.nearby_triangles(point,radius):
            # Fine scan triangles share grid cells. Their bounds cheaply
            # reject facets farther than the best exact result so far.
            if best is not None:
                squared_bound = sum(max(low-point[k], 0., point[k]-high)**2
                                    for k,(low,high) in enumerate(self.bounds[index]))
                if squared_bound >= best[0]:
                    continue
            triangle,normal=self.triangles[index]
            closest=closest_point_on_triangle(point,*triangle)
            delta=_sub(point,closest)
            squared=_dot(delta,delta)
            if best is None or squared<best[0]:
                distance=math.sqrt(squared)
                best=(squared,{"distance":distance,"signed_distance":math.copysign(distance,_dot(delta,normal)),
                               "point":list(closest),"normal":list(normal),"triangle_index":index})
        return None if best is None else best[1]


@lru_cache(maxsize=48)
def _local_candidates(radius,height,seed,detail="standard"):
    options = {} if detail == "standard" else {"detail": detail}
    mesh=generate_pocillopora_scan("bleached_alive",radius,height,seed,**options)
    surface=SurfaceQuery(mesh["points"],mesh["indices"],cell_size=.0125 if detail == "hero" else .025)
    maximum_z=max(p[2] for p in mesh["points"])
    preliminary=[]
    for index,(triangle,normal) in enumerate(surface.triangles):
        point=tuple(sum(p[k] for p in triangle)/3 for k in range(3))
        radial=math.hypot(*point[:2]); horizontal=math.hypot(*normal[:2])
        if point[2] < max(.10,maximum_z*.65) or abs(normal[2])>.32 or radial<radius*.35:
            continue
        outward=(normal[0]/horizontal,normal[1]/horizontal,0.)
        if (point[0]*outward[0]+point[1]*outward[1])/radial < .70:
            continue
        # Prefer high, outer branch faces whose crown projects into open water.
        score=point[2]/maximum_z + radial/radius*.65 - abs(normal[2])*.15
        preliminary.append((-score,index,point,outward))
    preliminary.sort()
    candidates=[]
    accepted=[]
    sampled_cells=set()
    for score,index,point,normal in preliminary:
        if detail == "hero":
            # Preserve real high-resolution facets while avoiding repeated
            # clearance work on dozens of almost coincident microtriangles.
            key=tuple(math.floor(v/.003) for v in point)
            if key in sampled_cells:
                continue
            sampled_cells.add(key)
        # Avoid hundreds of nearly identical microfacets on the same branch.
        if any(math.dist(point,p)<.006 for p in accepted):
            continue
        base=(point[0]+normal[0]*.0048,point[1]+normal[1]*.0048,point[2]-.020)
        # The thin basal stem can contact only the designated small patch.
        # Its upper crown must clear the pre-existing colony entirely.
        clear=True
        for z,r in ((.0,.004),(.010,.0045),(.020,.0045),(.035,.0045),(.050,.005),(.065,.008),(.080,.034),(.105,.045),(.135,.045)):
            query=surface.nearest((base[0],base[1],base[2]+z),radius=max(.025,r+.010))
            if query and query["signed_distance"] < r-.0020:
                clear=False;break
        if not clear:
            continue
        if detail == "hero":
            # The original specimen has much finer recesses than its reduced
            # preview mesh. Check an entire rotation-invariant basal envelope,
            # not just the centreline, before accepting those microfacets.
            ring_gaps=[]
            for z in (.01755,.02622,.03478):
                for angle_index in range(24):
                    angle=angle_index*math.tau/24
                    query=surface.nearest((base[0]+.006*math.cos(angle),
                                           base[1]+.006*math.sin(angle),base[2]+z),radius=.010)
                    if query is None or query["signed_distance"] < -.0022:
                        clear=False
                        break
                    ring_gaps.append(query["signed_distance"])
                if not clear:
                    break
            if not clear or min(ring_gaps)>.0008:
                continue
        # An unobstructed vertical insertion corridor above the clamped stem.
        for z in (.17,.23,.30):
            query=surface.nearest((base[0],base[1],base[2]+z),radius=.045)
            if query and query["signed_distance"]<.035:
                clear=False;break
        if not clear:
            continue
        support=surface.nearest(base,radius=.04)
        if not support or support["distance"]>.020:
            continue
        triangle=surface.triangles[index][0]
        candidates.append({"base":base,"point":point,"normal":normal,"score":-score,
                           "triangle_index":index,"triangle":triangle,
                           "patch_triangles":surface.nearby_triangles(point,.025),
                           "support_point":support["point"],
                           "source_vertex_count":len(mesh["points"]),
                           "source_triangle_count":len(mesh["indices"])//3})
        accepted.append(point)
    return tuple(candidates)


def natural_contact_candidates(coral,colony_seed,detail="standard"):
    """Independent world-space candidates from real colony branch triangles."""
    origin=coral["position"]
    result=[]
    if detail not in ("standard", "hero"):
        raise ValueError("Contact mesh detail must be standard or hero")
    for candidate in _local_candidates(float(coral["radius"]),float(coral["height"]),int(colony_seed),detail):
        item=dict(candidate)
        for key in ("base","point","support_point"):
            item[key]=list(_add(candidate[key],origin))
        item["triangle"]=[list(_add(p,origin)) for p in candidate["triangle"]]
        item["normal"]=list(candidate["normal"])
        item["patch_triangles"]=list(candidate["patch_triangles"])
        result.append(item)
    return result
