"""Reduced-order, deterministic fragment dynamics; not full fluid/rigid-body CFD."""
from __future__ import annotations
import numpy as np


def vehicle_step(position, velocity, command, current, dt, *, anchor=None,
                 mass=18., max_thrust=38., projected_area=.12,
                 water_density=1025.):
    """Integrate submerged translation with water drag and bounded thrusters.

    ``command`` is desired world velocity (m/s). A station-keeping ``anchor``
    adds position feedback; it never freezes the body or teleports it back.
    The vehicle is neutrally buoyant. Added mass, wave pressure and rotational
    dynamics are outside this reduced model; parameters are demo assumptions.
    Ten-millisecond substeps bound the velocity servo and quadratic drag.
    """
    p, v, desired, flow = (np.asarray(x, dtype=float).copy()
                            for x in (position, velocity, command, current))
    if any(x.shape != (3,) or not np.isfinite(x).all() for x in (p,v,desired,flow)):
        raise ValueError('Position, velocity, command and current must be finite 3-vectors')
    scalars = np.asarray([dt,mass,max_thrust,projected_area,water_density])
    if not np.isfinite(scalars).all() or np.any(scalars <= 0) or dt > .25:
        raise ValueError('Positive physical parameters and dt <= .25 seconds are required')
    fixed = None if anchor is None else np.asarray(anchor,dtype=float)
    if fixed is not None and (fixed.shape != (3,) or not np.isfinite(fixed).all()):
        raise ValueError('Station anchor must be a finite 3-vector')
    steps = int(np.ceil(dt/.01))
    h = dt/steps
    drag = thrust = np.zeros(3)
    peak_thrust = 0.
    for _ in range(steps):
        target = desired if fixed is None else desired + 2.*(fixed-p)
        # 4/s velocity controller; saturate the vector, not individual axes.
        thrust = mass*4.*(target-v)
        magnitude = float(np.linalg.norm(thrust))
        thrust *= min(1.,max_thrust/max(magnitude,1e-12))
        relative = flow-v
        drag = .5*water_density*1.05*projected_area*np.linalg.norm(relative)*relative
        v += (drag+thrust)/mass*h
        p += v*h
        peak_thrust=max(peak_thrust,float(np.linalg.norm(thrust)))
    return p.tolist(),v.tolist(),{
        'model':'neutrally buoyant translation / quadratic water drag / bounded thruster feedback',
        'current_velocity_m_s':flow.tolist(),'drag_force_n':drag.tolist(),
        'thrust_force_n':thrust.tolist(),'peak_thrust_n':peak_thrust,
        'station_error_m':float(np.linalg.norm(p-fixed)) if fixed is not None else None,
    }


def dropped_step(position, velocity, current, dt, floor=0.025):
    p, v, flow = (np.asarray(x, dtype=float) for x in (position, velocity, current))
    if p[2] <= floor and np.linalg.norm(v) < 1e-8:
        return p.tolist(), [0.,0.,0.]
    # Effective submerged weight and water drag; settle on the local bed.
    a = 2.6 * (flow-v) + np.array([0., 0., -.65])
    v = v + a*dt
    p = p + v*dt
    if p[2] <= floor:
        p[2] = floor
        v[:] = 0.
    return p.tolist(), v.tolist()


def push_response(*, stiffness=450., force=.18, duration=1.2, dt=.01,
                  mass=.025, damping=4., break_force=.35):
    """Integrate a submerged, compliant securing joint under a measured push.

    Semi-implicit substeps bound stiff-joint integration. A broken joint has
    no spring, so weak fixtures must fail rather than being declared stable.
    """
    x = v = peak = 0.
    broken = force > break_force
    rows=[]
    for i in range(round((duration+1.)/dt)):
        t=(i+1)*dt
        applied=force if t <= duration else 0.
        for _ in range(10):
            h=dt/10
            acceleration=(applied-(0. if broken else stiffness*x)-damping*v)/mass
            v+=acceleration*h
            x+=v*h
        peak=max(peak, abs(x))
        rows.append({'time':t,'displacement_m':x,'force_n':applied})
    return {'model':'reduced spring-damper attachment', 'force_n':force,
            'stiffness_n_m':stiffness,'break_force_n':break_force,
            'peak_displacement_m':peak,'residual_displacement_m':abs(x),
            'broken':broken,'stable':not broken and peak < .002 and abs(x)<.0005,
            'samples':rows}
