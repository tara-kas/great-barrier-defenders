"""Reduced-order, deterministic fragment dynamics; not full fluid/rigid-body CFD."""
from __future__ import annotations
import numpy as np


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
