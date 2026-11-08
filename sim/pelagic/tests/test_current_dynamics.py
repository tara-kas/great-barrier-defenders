"""Physical behavior checks independent of rendering or a fixed mission trace."""
import math
import numpy as np
import pytest
from reefsim.reef_motion import flow_velocity, flow_displacement, tracer_pose
from reefsim.team_physics import vehicle_step


def test_tracer_velocity_matches_coral_driving_flow_and_is_history_free():
    current=[.10,.035,0.]
    for time in (.2,1.,3.2,20.,71.):
        epsilon=1e-5
        left=flow_displacement(current,time-epsilon)
        right=flow_displacement(current,time+epsilon)
        derivative=[(b-a)/(2*epsilon) for a,b in zip(left,right)]
        assert np.allclose(derivative,flow_velocity(current,time),atol=1e-9)
    reference=tracer_pose([0.,0.,1.],20.,current)
    tracer_pose([0.,0.,1.],200.,current)
    assert tracer_pose([0.,0.,1.],20.,current)==reference
    assert np.allclose(tracer_pose([.1,.2,1.],100.,[0.,0.,0.])['position'],[.1,.2,1.])


def test_particle_wrap_is_hidden_at_both_volume_edges():
    # Travel crosses x=+9 and reappears at -9 with zero width/opacity.
    at=tracer_pose([9.,0.,1.],0.,[0.,0.,0.])
    before=tracer_pose([9.-1e-6,0.,1.],0.,[0.,0.,0.])
    after=tracer_pose([-9.+1e-6,0.,1.],0.,[0.,0.,0.])
    assert at['opacity']==0.
    assert before['opacity']<1e-9 and after['opacity']<1e-9
    assert tracer_pose([0.,0.,1.],0.,[0.,0.,0.])['opacity']==1.


def test_station_keeping_responds_to_current_without_teleporting():
    p=[0.,0.,1.];v=[0.,0.,0.]; anchor=p[:]
    peak=0.;peak_step=0.
    for i in range(600):
        previous=p[:]
        p,v,info=vehicle_step(p,v,[0.,0.,0.],flow_velocity([.10,.035,0.],i*.05),.05,anchor=anchor)
        peak=max(peak,info['station_error_m'])
        peak_step=max(peak_step,math.dist(previous,p))
        assert info['peak_thrust_n']<=38.+1e-10
    assert .001 < peak < .025
    assert peak_step < .001
    assert info['drag_force_n'][0]>0.
    assert info['thrust_force_n'][0]<0.
    still=vehicle_step(anchor,[0.,0.,0.],[0.,0.,0.],[0.,0.,0.],.05,anchor=anchor)
    assert still[:2]==(anchor,[0.,0.,0.])


def test_drag_moves_unpowered_vehicle_and_force_limit_is_real():
    p=[0.,0.,1.];v=[0.,0.,0.]
    for _ in range(100):
        p,v,info=vehicle_step(p,v,[0.,0.,0.],[.2,0.,0.],.05,max_thrust=.0001)
    assert p[0]>.2 and v[0]>0.
    _,v,info=vehicle_step([0.,0.,1.],[0.,0.,0.],[100.,100.,0.],[0.,0.,0.],.05)
    assert info['peak_thrust_n']==pytest.approx(38.)
    assert np.linalg.norm(v)<38./18.*.05


def test_station_response_is_stable_when_step_size_changes():
    def run(dt):
        p=[0.,0.,1.];v=[0.,0.,0.]
        for _ in range(round(10/dt)):
            p,v,_=vehicle_step(p,v,[0.,0.,0.],[.15,.035,0.],dt,anchor=[0.,0.,1.])
        return p,v
    p1,v1=run(.05);p2,v2=run(.01)
    assert np.allclose(p1,p2,atol=1e-12)
    assert np.allclose(v1,v2,atol=1e-12)
    with pytest.raises(ValueError):vehicle_step([0.,0.,0.],[0.,0.,0.],[0.,0.,0.],[0.,0.,0.],1.)
