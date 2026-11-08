"""Anchored soft-coral geometry and a reduced-order current response.

Hard reef-building coral skeletons should remain rigid. This module supplies
small flexible sea-fan/gorgonian-like background colonies instead. It is an
artistic soft-coral form, not a species model or a calibrated tissue simulation.

Horizontal drag drives a damped mass/spring bending coordinate, solved in
closed form for a mean current plus oscillatory surge. Quadratic drag is
resolved into six Fourier harmonics; the same velocity drives diagnostics. Each
pose depends on absolute time and the current supplied for that frame. It is
therefore reproducible when a recorder skips frames. A changing current is
treated as a new constant-for-the-episode input, not integrated flow history.
The root is fixed and a smooth geometric limiter prevents extreme folding.
Only points and normals change; topology and biological health never change.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache
from collections import OrderedDict

try:
    import numpy as _np
except ImportError:  # The mission and geometry still run with the standard library.
    _np = None


_rest_arrays = OrderedDict()


def _numpy_rest(mesh, kind):
    """Small content-checked cache; no hidden mutation or stale rest geometry.

    Signature tuples retain immutable copies of any list-valued input rows.
    Checking them is cheaper than reconstructing every array at video rate.
    The cache keeps no reference to the mutable input dictionary, and both
    content and shape are checked even if Python reuses a dictionary's id.
    """
    metadata = mesh["motion"]
    points = tuple(map(tuple,mesh["points"]))
    normals = tuple(map(tuple,mesh["normals"]))
    if kind == "fan":
        extra = (metadata["root_height"],metadata["height"])
    else:
        extra = (tuple(metadata["owners"]),tuple(metadata["weights"]),
                 tuple(metadata["slopes"]),tuple(tuple(p["normal"]) for p in metadata["polyps"]))
    signature = (points,normals,extra)
    key = (kind,id(mesh))
    saved = _rest_arrays.get(key)
    if saved is not None and saved[0] == signature:
        _rest_arrays.move_to_end(key)
        return saved[1]
    data = {"points":_np.asarray(points,dtype=_np.float64),
            "normals":_np.asarray(normals,dtype=_np.float64)}
    if kind == "fan":
        root,height = extra
        span = height-root
        q = _np.clip((data["points"][:,2]-root)/span,0.,1.)
        data["weights"] = .5*q*q*(3.-q)
        data["derivatives"] = _np.where((data["points"][:,2]>root)&(data["points"][:,2]<height),
                                        1.5*q*(2.-q)/span,0.)
    else:
        owners,weights,slopes,surface_normals = extra
        owners = _np.asarray(owners,dtype=_np.int64)
        weights = _np.asarray(weights,dtype=_np.float64)
        slopes = _np.asarray(slopes,dtype=_np.float64)
        active = (owners>=0)&(weights!=0)
        data.update(active=active,ids=owners[active],weights=weights[active],slopes=slopes[active],
            surface_normals=_np.asarray(surface_normals,dtype=_np.float64)[owners[active]])
    for array in data.values():
        array.setflags(write=False)
    _rest_arrays[key] = (signature,data)
    _rest_arrays.move_to_end(key)
    while len(_rest_arrays)>64:
        _rest_arrays.popitem(last=False)
    return data

from .organic import _Builder, _curve


def _number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return float(value)


def _unit(vector):
    length = math.sqrt(sum(v*v for v in vector))
    return tuple(v / length for v in vector) if length > 1e-12 else (0., 0., 1.)


def generate_soft_coral(seed, height=.3, radius=.16, health="healthy"):
    """Return a compact connected fan mesh with motion metadata.

    The standard mesh keys match ``organic.generate_coral``. Extra ``motion``
    metadata is consumed only by ``current_pose``. Positions are local, Z-up;
    a scene can place the resulting mesh on reef pavement in a clear patch.
    All colonies use fewer than 4,000 vertices, with stable seeded geometry.
    """
    height = _number(height, "height", positive=True)
    radius = _number(radius, "radius", positive=True)
    if health not in ("healthy", "bleached_alive", "dead"):
        raise ValueError("Unsupported coral health")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    rng = random.Random(seed)
    builder = _Builder()
    palette = ((.45, .22, .12), (.43, .25, .39), (.53, .36, .16), (.37, .27, .20))
    base = palette[seed % len(palette)]
    if health == "bleached_alive":
        base = (.76, .69, .60)
    elif health == "dead":
        base = (.25, .28, .18)
    tip = tuple(min(1., c * .78 + .16) for c in base)
    stalk = ((0., 0., 0.), (0., 0., height * .055),
             (radius * .018, 0., height * .12), (0., 0., height * .20))
    builder.curved_tube(stalk, radius * .035, base, base, .1,
                        polyp=False, segments=7, sides=7)
    controls = []
    # Thirteen unequal ribs and three cross-link bands retain a porous,
    # irregular silhouette when foreground fans are rendered at larger scale.
    for i in range(13):
        angle = -1.18 + i * 2.36 / 12
        angle += rng.uniform(-.055, .055)
        end = (radius * math.sin(angle) * rng.uniform(.91, 1.02),
               radius * rng.uniform(-.085, .085),
               min(height*.98, height * (.35 + .61 * math.cos(angle)) * rng.uniform(.94,1.03)))
        root = (0., 0., height * .135)
        control = (root, (end[0] * .08, end[1] * .15, height * .35),
                   (end[0] * .76, end[1] * .75, end[2] * .84), end)
        controls.append(control)
        builder.curved_tube(control, radius * rng.uniform(.018, .024), base, tip, angle,
                            polyp=False, segments=8, sides=6)
        for t in (.62, .82):
            point, tangent = _curve(control, t)
            sign = -1 if i < 6 else 1
            twig_end = (point[0] + sign * radius * .11,
                        point[1] + radius * rng.uniform(-.025, .025),
                        min(height, point[2] + height * rng.uniform(.08, .15)))
            twig = (point, tuple(point[j] + tangent[j] * height * .035 for j in range(3)),
                    tuple((point[j] + twig_end[j]) * .5 for j in range(3)), twig_end)
            builder.curved_tube(twig, radius * .010, base, tip, angle + t,
                                polyp=False, segments=5, sides=5)
        if health != "dead":
            # Small attached calices suggest living tissue without moving a
            # mineral skeleton or fabricating new polyps during an episode.
            for t in (.47, .69, .89):
                point, tangent = _curve(control, t)
                anchor = (point[0], point[1] - radius * .018, point[2])
                builder.calice(anchor, (0., -1., 0.), tangent,
                               max(.0006, radius * .012), tip)
    # Anastomosing cross-links tie adjacent ribs into a net-like structure.
    for i in range(12):
        for t in (.48, .68, .86):
            a, _ = _curve(controls[i], t)
            b, _ = _curve(controls[i + 1], t + rng.uniform(-.03, .03))
            c = tuple((a[j] + b[j]) * .5 for j in range(3))
            control = (a, (c[0], c[1], c[2] - height * .018), c, b)
            builder.curved_tube(control, radius * .007, base, tip, i + t,
                                polyp=False, segments=4, sides=5)
    mesh = builder.data
    mesh["motion"] = {
        "height": height, "radius": radius, "health": health,
        "phase": rng.uniform(-math.pi, math.pi),
        "root_height": min(.015, height * .08),
        "projected_area": 2. * radius * height * .055,
        "max_displacement": min(radius * .45, (height - min(.015, height * .08)) * .20),
        "model": "anchored soft-coral damped bending under quadratic oscillatory drag; uncalibrated reduced-order model",
    }
    return mesh


def _response(time, force, amplitude, frequency, phase, mass, damping, stiffness):
    """Exact zero-initial-condition spring response to constant + sine force."""
    denominator_real = stiffness - mass * frequency * frequency
    denominator_imag = damping * frequency
    harmonic_amplitude = amplitude / math.hypot(denominator_real, denominator_imag)
    harmonic_phase = phase - math.atan2(denominator_imag, denominator_real)
    particular = force / stiffness + harmonic_amplitude * math.sin(frequency * time + harmonic_phase)
    y0 = -(force / stiffness + harmonic_amplitude * math.sin(harmonic_phase))
    v0 = -harmonic_amplitude * frequency * math.cos(harmonic_phase)
    alpha = damping / (2. * mass)
    discriminant = alpha * alpha - stiffness / mass
    if abs(discriminant) <= 1e-8:
        homogeneous = math.exp(-alpha * time) * (y0 + (v0 + alpha * y0) * time)
    elif discriminant < 0:
        beta = math.sqrt(-discriminant)
        homogeneous = math.exp(-alpha * time) * (
            y0 * math.cos(beta * time) + (v0 + alpha * y0) / beta * math.sin(beta * time))
    else:
        beta = math.sqrt(discriminant)
        # This form avoids cancellation in the slow overdamped root.
        fast = -alpha - beta
        slow = (stiffness / mass) / fast
        a = (v0 - fast * y0) / (slow - fast)
        b = y0 - a
        homogeneous = a * math.exp(slow * time) + b * math.exp(fast * time)
    return particular + homogeneous


def _wave_parameters(surge_ratio, surge_period, cross_flow_ratio, phase_offset):
    surge_ratio = _number(surge_ratio, "surge_ratio")
    surge_period = _number(surge_period, "surge_period", positive=True)
    cross_flow_ratio = _number(cross_flow_ratio, "cross_flow_ratio")
    phase_offset = _number(phase_offset, "phase_offset")
    if not 0 <= surge_ratio <= 2 or not 0 <= cross_flow_ratio <= 1:
        raise ValueError("surge_ratio must be 0–2; cross_flow_ratio must be 0–1")
    return surge_ratio, surge_period, cross_flow_ratio, phase_offset


def flow_velocity(current, time, *, surge_ratio=.8, surge_period=6.5,
                  cross_flow_ratio=.25, phase_offset=0.):
    """Actual illustrative water velocity used to drive the fan's drag.

    Mean horizontal flow defines the along/cross basis. Surge and transverse
    velocity scale with that mean, so a zero-current control stays stationary.
    ``phase_offset`` can encode a small spatial wave delay in radians.
    """
    if not isinstance(current, (list, tuple)) or len(current) != 3:
        raise ValueError("current must contain three components")
    current = tuple(_number(v, "current") for v in current)
    time = _number(time, "time")
    if time < 0:
        raise ValueError("time must be nonnegative")
    surge_ratio, surge_period, cross_flow_ratio, phase_offset = _wave_parameters(
        surge_ratio, surge_period, cross_flow_ratio, phase_offset)
    angle = math.tau * time / surge_period + phase_offset
    along = 1. + surge_ratio * math.sin(angle)
    cross = cross_flow_ratio * math.cos(angle)
    return [current[0] * along - current[1] * cross,
            current[1] * along + current[0] * cross, current[2]]


def flow_displacement(current, time, *, surge_ratio=.8, surge_period=6.5,
                      cross_flow_ratio=.25, phase_offset=0.):
    """Analytic integral of ``flow_velocity`` from zero to ``time``.

    Passive suspended tracers use the same surge as flexible coral drag.
    Evaluation is independent of frame rate, frame skipping and rewind.
    """
    # Share validation with the driving velocity field.
    flow_velocity(current,time,surge_ratio=surge_ratio,surge_period=surge_period,
                  cross_flow_ratio=cross_flow_ratio,phase_offset=phase_offset)
    frequency=math.tau/surge_period
    angle=frequency*time+phase_offset
    along=time+surge_ratio*(math.cos(phase_offset)-math.cos(angle))/frequency
    cross=cross_flow_ratio*(math.sin(angle)-math.sin(phase_offset))/frequency
    return [current[0]*along-current[1]*cross,
            current[1]*along+current[0]*cross,current[2]*time]


def tracer_pose(origin, time, current, *, settling_speed=0., width=18.,
                length=18., height=6.3, bottom=.1, fade_margin=.20):
    """Current-driven suspended particle with faded, seamless volume wrapping.

    Opacity reaches zero at each volume edge, hiding its wrap into the opposite
    edge. ``settling_speed`` models slow downward sediment settling in m/s;
    use zero for neutrally buoyant tracers and the still-water control.
    """
    if not isinstance(origin,(list,tuple)) or len(origin)!=3:
        raise ValueError('Origin must contain three components')
    origin=tuple(_number(v,'origin') for v in origin)
    width=_number(width,'width',positive=True)
    length=_number(length,'length',positive=True)
    height=_number(height,'height',positive=True)
    bottom=_number(bottom,'bottom')
    fade_margin=_number(fade_margin,'fade_margin',positive=True)
    settling_speed=_number(settling_speed,'settling_speed')
    if settling_speed<0:
        raise ValueError('Settling speed cannot be negative')
    shift=flow_displacement(current,time)
    shift[2]-=settling_speed*time
    limits=((-width*.5,width),(-length*.5,length),(bottom,height))
    result=[];opacity=1.
    for value,delta,(low,span) in zip(origin,shift,limits):
        wrapped=(value+delta-low)%span
        result.append(low+wrapped)
        edge=min(wrapped,span-wrapped)
        u=max(0.,min(1.,edge/min(fade_margin,span*.5)))
        opacity*=u*u*(3.-2.*u)
    return {'position':result,'opacity':opacity}


@lru_cache(maxsize=64)
def _drag_harmonics(surge_ratio, cross_flow_ratio):
    """Six-harmonic representation of v*|v| for the configured wave cycle."""
    samples = 128
    angles = [math.tau * i / samples for i in range(samples)]
    loads = []
    for angle in angles:
        along = 1. + surge_ratio * math.sin(angle)
        cross = cross_flow_ratio * math.cos(angle)
        speed = math.hypot(along, cross)
        loads.append((along * speed, cross * speed))
    axes = []
    for axis in range(2):
        mean = sum(load[axis] for load in loads) / samples
        harmonics = []
        for harmonic in range(1, 7):
            cosine = 2. / samples * sum(load[axis] * math.cos(harmonic * angle)
                                       for load, angle in zip(loads, angles))
            sine = 2. / samples * sum(load[axis] * math.sin(harmonic * angle)
                                     for load, angle in zip(loads, angles))
            amplitude = math.hypot(cosine, sine)
            if amplitude > 1e-10:
                harmonics.append((harmonic, amplitude, math.atan2(cosine, sine)))
        axes.append((mean, tuple(harmonics)))
    return tuple(axes)


def _tip_response(time, velocity, metadata, stiffness, damping, mass,
                  drag_coefficient, water_density, surge_ratio, surge_period,
                  cross_flow_ratio, phase_offset):
    speed = math.hypot(velocity[0], velocity[1])
    if speed <= 1e-12 or time <= 0 or metadata["health"] == "dead":
        return (0., 0.)
    force = (.5 * water_density * drag_coefficient * metadata["projected_area"]
             * min(speed, 20.) ** 2)
    frequency = math.tau / surge_period
    coordinates = []
    for mean, harmonics in _drag_harmonics(surge_ratio, cross_flow_ratio):
        value = _response(time, force * mean, 0., frequency, 0., mass, damping, stiffness)
        for harmonic, amplitude, phase in harmonics:
            value += _response(time, 0., force * amplitude, frequency * harmonic,
                               phase + harmonic * phase_offset, mass, damping, stiffness)
        coordinates.append(value)
    along, cross = coordinates
    ux, uy = velocity[0] / speed, velocity[1] / speed
    dx, dy = along * ux - cross * uy, along * uy + cross * ux
    length = math.hypot(dx, dy)
    limit = metadata["max_displacement"]
    if length > 1e-15:
        scale = limit * math.tanh(length / limit) / length
        return dx * scale, dy * scale
    return (0., 0.)


def current_pose(mesh, time, current, *, stiffness=1.2, damping=.8, mass=.05,
                 drag_coefficient=1.1, water_density=1025., surge_ratio=.8,
                 surge_period=6.5, cross_flow_ratio=.25, phase_offset=0.,
                 accelerated=None):
    """Deform the rest mesh under horizontal current, preserving its root.

    Parameters are an illustrative lumped spring (N/m), damping (N s/m),
    effective moving mass (kg), drag coefficient and water density (kg/m³).
    Force is 0.5*rho*Cd*A*v*|v| under ``flow_velocity``. Vertical flow is accepted but this reduced
    bending coordinate models only XY flow; there is no axial stretch.
    Analytic inverse-transpose normals follow the shear deformation.
    NumPy accelerates vertex deformation when installed; ``accelerated=False``
    forces the standard-library path. Both return lists of float tuples and
    leave the rest mesh untouched; the bounded rest-array cache checks content
    on every evaluation, including externally edited rest geometry.
    """
    time = _number(time, "time")
    if time < 0:
        raise ValueError("time must be nonnegative")
    if not isinstance(current, (list, tuple)) or len(current) != 3:
        raise ValueError("current must contain three components")
    velocity = tuple(_number(v, "current") for v in current)
    stiffness = _number(stiffness, "stiffness", positive=True)
    damping = _number(damping, "damping", positive=True)
    mass = _number(mass, "mass", positive=True)
    drag_coefficient = _number(drag_coefficient, "drag_coefficient", positive=True)
    water_density = _number(water_density, "water_density", positive=True)
    surge_ratio, surge_period, cross_flow_ratio, phase_offset = _wave_parameters(
        surge_ratio, surge_period, cross_flow_ratio, phase_offset)
    metadata = mesh["motion"]
    if accelerated is not None and not isinstance(accelerated, bool):
        raise ValueError("accelerated must be True, False or None")
    response_args = (velocity, metadata, stiffness, damping, mass, drag_coefficient,
                     water_density, surge_ratio, surge_period, cross_flow_ratio, phase_offset)
    displacement = _tip_response(time, *response_args)
    points, normals = [], []
    root = metadata["root_height"]
    span = metadata["height"] - root
    dx, dy = displacement
    if _np is not None and accelerated is not False and mesh["points"]:
        rest = _numpy_rest(mesh,"fan")
        result = rest["points"].copy()
        normal_array = rest["normals"].copy()
        weight,derivative = rest["weights"],rest["derivatives"]
        result[:,0] += dx*weight
        result[:,1] += dy*weight
        normal_array[:,2] -= derivative*(dx*normal_array[:,0]+dy*normal_array[:,1])
        size = _np.sqrt(normal_array[:,0]**2+normal_array[:,1]**2+normal_array[:,2]**2)
        valid = size>1e-12
        normal_array[valid] /= size[valid,None]
        normal_array[~valid] = (0.,0.,1.)
        points = list(map(tuple,result.tolist()))
        normals = list(map(tuple,normal_array.tolist()))
    else:
        for point, normal in zip(mesh["points"], mesh["normals"]):
            q = max(0., min(1., (point[2] - root) / span))
            weight = .5 * q*q * (3. - q)
            derivative = 1.5 * q * (2. - q) / span if root < point[2] < metadata["height"] else 0.
            points.append((point[0] + dx * weight, point[1] + dy * weight, point[2]))
            normals.append(_unit((normal[0], normal[1],
                                  normal[2] - derivative * (dx * normal[0] + dy * normal[1]))))
    epsilon = .001
    before = _tip_response(max(0., time - epsilon), *response_args)
    after = _tip_response(time + epsilon, *response_args)
    interval = epsilon + min(time, epsilon)
    shear = 1.5 * math.hypot(dx, dy) / span
    return {"points": points, "normals": normals,
            "tip_displacement": list(displacement),
            "tip_velocity": ([(after[i] - before[i]) / interval for i in range(2)]
                             if time > 0 else [0.,0.]),
            "flow_velocity": flow_velocity(current, time, surge_ratio=surge_ratio,
                surge_period=surge_period, cross_flow_ratio=cross_flow_ratio, phase_offset=phase_offset),
            "max_shear": shear,
            "max_extension_ratio": (math.sqrt(4. + shear * shear) + shear) / 2.,
            "model": metadata["model"]}
