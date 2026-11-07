"""Soft living-polyp patches on a rigid coral surface.

The host colony is never deformed. Only authored tentacle vertices move under
a local tangential, damped-drag approximation; basal cups remain fixed. These
are enlarged visual polyps, not a calibrated Pocillopora tissue model.
"""
from __future__ import annotations

import math
import random

from .organic import _Builder, _add, _mul, _cross, _dot
from .reef_motion import _number, _unit, _tip_response, _wave_parameters, _np, _numpy_rest


def _vector(value, name):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError(f"{name} must contain three components")
    return tuple(_number(component, name) for component in value)


def generate_polyp_patch(anchors, seed=26, health="healthy", tentacle_length=.008,
                         tentacles=12):
    """Make tissue on supplied local-space surface points and normals.

    ``anchors`` is a sequence of dictionaries containing ``point``, ``normal``
    and optional RGB ``color``. About 16–24 well-spaced anchors on a hero colony
    are enough. The sixfold/12-tentacle layout is a visual hexacorallian cue;
    ``tentacle_length`` is in enlarged scene metres, not specimen measurements.
    Dead controls return an empty patch; no living tissue is added to them.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if health not in ("healthy", "bleached_alive", "dead"):
        raise ValueError("Unsupported coral health")
    tentacle_length = _number(tentacle_length, "tentacle_length", positive=True)
    if not .002 <= tentacle_length <= .015:
        raise ValueError("tentacle_length must be .002–.015 metres")
    if tentacles not in (6, 12):
        raise ValueError("tentacles must be 6 or 12")
    if not isinstance(anchors, (tuple, list)) or len(anchors) > 128:
        raise ValueError("anchors must be a sequence with at most 128 entries")
    validated = []
    for anchor in anchors:
        point = _vector(anchor["point"], "point")
        normal = _vector(anchor["normal"], "normal")
        if math.hypot(*normal) < 1e-10:
            raise ValueError("surface normal must be nonzero")
        color = _vector(anchor.get("color", (.62,.43,.32)), "color")
        validated.append((point, _unit(normal), color))
    builder = _Builder()
    owners, weights, slopes, records = [], [], [], []
    rng = random.Random(seed)
    if health != "dead":
        for number, (point, normal, pigment) in enumerate(validated):
            ref = (1.,0.,0.) if abs(normal[2]) > .8 else (0.,0.,1.)
            u = _unit(_cross(normal, ref))
            v = _unit(_cross(normal, u))
            length = tentacle_length * rng.uniform(.82 if health == "bleached_alive" else .94, 1.)
            color = tuple(pigment[i]*.55 + ((.91,.79,.71) if health == "bleached_alive"
                                          else (.75,.61,.48))[i]*.45 for i in range(3))
            # The calice and mouth stay attached to the existing scan surface.
            builder.calice(point, normal, u, length*.19, color)
            owners.extend([-1] * (len(builder.data["points"]) - len(owners)))
            weights.extend([0.] * (len(owners)-len(weights)))
            slopes.extend([0.] * (len(owners)-len(slopes)))
            root_height, span = length*.15, length*.57
            records.append({"point": point, "normal": normal, "u": u, "v": v,
                            "phase_offset": rng.uniform(-.12,.12),
                            "health": health, "projected_area": length*length*.25,
                            "max_displacement": span*.27})
            for tentacle in range(tentacles):
                angle = tentacle * math.tau / tentacles + rng.uniform(-.045,.045)
                radial = _add(_mul(u, math.cos(angle)), _mul(v, math.sin(angle)))
                base = _add(point, _add(_mul(normal, root_height), _mul(radial,length*.12)))
                control = (base,
                    _add(point, _add(_mul(normal, length*.43), _mul(radial,length*.19))),
                    _add(point, _add(_mul(normal, length*.78), _mul(radial,length*.47))),
                    _add(point, _add(_mul(normal, length*.72), _mul(radial,length*.60))))
                first = len(builder.data["points"])
                builder.curved_tube(control, length*.045, color,
                    tuple(min(1.,c*1.06) for c in color), angle,
                    polyp=False, segments=4, sides=4)
                for vertex in builder.data["points"][first:]:
                    height = _dot(tuple(vertex[i]-point[i] for i in range(3)), normal)
                    q = max(0., min(1., (height-root_height)/span))
                    owners.append(number)
                    weights.append(q*q*(3.-2.*q))
                    slopes.append(6.*q*(1.-q)/span if 0 < q < 1 else 0.)
    mesh = builder.data
    mesh["motion"] = {"polyps": records, "owners": owners, "weights": weights,
                      "slopes": slopes, "health": health,
                      "model": "anchored soft tentacles under local tangential damped drag; uncalibrated enlarged visual model"}
    return mesh


def polyp_current_pose(mesh, time, current, *, stiffness=.06, damping=.018,
                       mass=.00035, drag_coefficient=1.1, water_density=1025.,
                       surge_ratio=.8, surge_period=6.5, cross_flow_ratio=.25,
                       phase_offset=0., accelerated=None):
    """Return moved soft tissue and diagnostics; the rigid host is untouched.

    NumPy is optional and selected automatically. ``accelerated=False`` uses
    standard-library deformation; both return the same list/tuple interface.
    """
    time = _number(time, "time")
    if time < 0:
        raise ValueError("time must be nonnegative")
    current = _vector(current, "current")
    parameters = [_number(value, name, positive=True) for value, name in (
        (stiffness,"stiffness"), (damping,"damping"), (mass,"mass"),
        (drag_coefficient,"drag_coefficient"), (water_density,"water_density"))]
    stiffness, damping, mass, drag_coefficient, water_density = parameters
    surge_ratio, surge_period, cross_flow_ratio, phase_offset = _wave_parameters(
        surge_ratio, surge_period, cross_flow_ratio, phase_offset)
    metadata = mesh["motion"]
    if accelerated is not None and not isinstance(accelerated, bool):
        raise ValueError("accelerated must be True, False or None")
    displacements = []
    for polyp in metadata["polyps"]:
        local_current = [_dot(current, polyp["u"]), _dot(current, polyp["v"]), 0.]
        dx,dy = _tip_response(time, local_current, polyp, stiffness, damping, mass,
            drag_coefficient, water_density, surge_ratio, surge_period, cross_flow_ratio,
            phase_offset + polyp["phase_offset"])
        displacements.append(_add(_mul(polyp["u"],dx),_mul(polyp["v"],dy)))
    points, normals = [], []
    peak, max_shear = 0., 0.
    if _np is not None and accelerated is not False and mesh["points"]:
        rest = _numpy_rest(mesh,"polyp")
        result = rest["points"].copy()
        normal_array = rest["normals"].copy()
        active,ids = rest["active"],rest["ids"]
        weights,slopes = rest["weights"],rest["slopes"]
        displacement = _np.asarray(displacements,dtype=_np.float64)[ids]
        surface_normals = rest["surface_normals"]
        result[active] += displacement*weights[:,None]
        n = normal_array[active]
        dot = displacement[:,0]*n[:,0]+displacement[:,1]*n[:,1]+displacement[:,2]*n[:,2]
        n -= surface_normals*(slopes*dot)[:,None]
        size = _np.sqrt(n[:,0]**2+n[:,1]**2+n[:,2]**2)
        valid = size>1e-12
        n[valid] /= size[valid,None]
        n[~valid] = (0.,0.,1.)
        normal_array[active] = n
        lengths = _np.asarray([math.hypot(*d) for d in displacements],dtype=_np.float64)[ids]
        peak = float(_np.max(lengths*weights)) if ids.size else 0.
        max_shear = float(_np.max(lengths*slopes)) if ids.size else 0.
        points = list(map(tuple,result.tolist()))
        normals = list(map(tuple,normal_array.tolist()))
    else:
        for point, normal, owner, weight, slope in zip(mesh["points"], mesh["normals"],
                metadata["owners"], metadata["weights"], metadata["slopes"]):
            if owner < 0 or weight == 0:
                points.append(point)
                normals.append(normal)
                continue
            displacement = displacements[owner]
            points.append(_add(point,_mul(displacement,weight)))
            surface_normal = metadata["polyps"][owner]["normal"]
            normals.append(_unit(_add(normal,_mul(surface_normal,-slope*_dot(displacement,normal)))))
            peak=max(peak,math.hypot(*displacement)*weight)
            max_shear=max(max_shear,math.hypot(*displacement)*slope)
    return {"points": points, "normals": normals,
            "max_displacement": peak, "max_shear": max_shear,
            "max_extension_ratio": (math.sqrt(4. + max_shear * max_shear) + max_shear) / 2.,
            "polyp_count": len(metadata["polyps"]), "model": metadata["model"]}
