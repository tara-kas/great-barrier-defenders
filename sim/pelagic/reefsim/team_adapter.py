"""Team RobotInterface wired to the offline reef runtime.

The team FSM chooses pairs, navigates, detects loss and requests same-ID
recovery. The adapter supplies reduced dynamics and concrete manipulation.
The default sensor backend is explicitly synthetic and makes no model call.
"""
from __future__ import annotations
import copy
import math
import numpy as np
from agent.robot_interface import RobotInterface, Pose, RGBDFrame
from agent.graft_point import GraftCandidate
from .core import ReefSimulation, distance
from .team_physics import dropped_step, push_response, vehicle_step
from .reef_motion import flow_velocity


class ReefRobotAdapter(RobotInterface):
    def __init__(self, config, *, inject_drop=True, capture=True):
        self.sim=ReefSimulation(config)
        self.worker=self.sim.robots[1]
        self.worker['state']='PLAN'
        self.worker['wrist_yaw']=0.
        self.worker['position']=[-2.9,-3.4,1.3]
        self.worker['gripper_world']=self.sim._stowed_gripper(self.worker)
        self.sim.robots[0]['position']=[-3.8,-1.8,1.8]
        self.sim.robots[0]['state']='SURVEY'
        self.sim.robots[0]['gripper_world']=self.sim._stowed_gripper(self.sim.robots[0])
        self.command=np.zeros(3); self.locked=False; self.station_anchor=None
        self.frames=[]; self.capture=capture
        self.inject_drop=inject_drop; self.drop_done=False; self.carry_elapsed=0.
        self.active_fragment=None; self.recipient=None; self.source=None
        self.drop_velocity=[0.,0.,0.]; self.audit=[]; self.push_tests=[]
        self.fsm_state='SURVEY_SEABED'; self.manual_jaw=False
        self._record()

    def get_sim_time(self): return self.sim.time
    def get_pose(self):
        yaw=self.worker['yaw']
        return Pose(tuple(self.worker['position']),(0.,0.,math.sin(yaw/2),math.cos(yaw/2)))
    def set_cmd_vel(self, linear, angular): self.command=np.asarray(linear,dtype=float)
    def lock_base(self): self.locked=True; self.command[:]=0
    def unlock_base(self): self.locked=False
    def held_fragment_id(self): return self.worker.get('fragment_id') if self.fragment_held() else None
    def fragment_held(self):
        f=self.active_fragment
        return bool(f and f['stage']=='carried' and self.worker['carrying'])
    def on_fsm_transition(self,state):
        self.fsm_state=getattr(state,'value',str(state))
        names={'SURVEY_SEABED':'SURVEY','COMPUTE_RESTORATION_PLAN':'PLAN',
               'NAVIGATE_TO_DONOR':'NAVIGATE_TO_PICKUP','NAVIGATE_TO_RECIPIENT':'NAVIGATE_TO_SITE',
               'RECOVER_FRAGMENT':'RECOVER_FRAGMENT','RETURN_VISIT':'COMPLETE'}
        if self.fsm_state in names: self.worker['state']=names[self.fsm_state]
    def _record(self):
        if not self.capture: return
        state=self.sim.snapshot()
        state['team_mission']={'controller':'mission.runner / MissionFSM',
            'fsm_state':self.fsm_state,'perception':'OFFLINE DEMO / synthetic sensors; no Gemini call',
            'drop_injected':self.drop_done,'push_tests':copy.deepcopy(self.push_tests),
            'latest_evidence':copy.deepcopy(self.audit[-1]) if self.audit else None}
        self.frames.append(state)
    def _grasp_offset(self,f):
        p=f.get('grasp_point',[0.,0.,f.get('grasp_z',.045)])
        c,s=math.cos(f['yaw']),math.sin(f['yaw'])
        return [c*p[0]-s*p[1],s*p[0]+c*p[1],p[2]]
    def _sync(self):
        f=self.active_fragment
        if f and '_grip_heading_offset' in f:
            self.worker['wrist_yaw']=(f['yaw']+f['_grip_heading_offset']-self.worker['yaw']+math.pi)%(2*math.pi)-math.pi
        if not self.manual_jaw: self.worker['gripper_world']=self.sim._stowed_gripper(self.worker)
        if f and f['stage']=='carried':
            off=self._grasp_offset(f)
            f['position']=[self.worker['gripper_world'][i]-off[i] for i in range(3)]
            f['base_world']=f['position'][:]
    def wait(self, seconds):
        remaining=seconds
        while remaining>1e-9:
            dt=min(.05,remaining); remaining-=dt
            self.sim.time+=dt
            w=self.worker
            desired=np.zeros(3) if self.locked else self.command
            if self.locked and self.station_anchor is None:
                self.station_anchor=w['position'][:]
            elif not self.locked:
                self.station_anchor=None
            old=np.asarray(w['position'])
            flow=flow_velocity(self.sim.water['current'],self.sim.time)
            position,velocity,diagnostics=vehicle_step(w['position'],w['velocity'],desired,flow,dt,
                anchor=self.station_anchor,mass=self.sim.config['robot']['mass'],
                max_thrust=self.sim.config['robot']['max_thrust'],water_density=self.sim.config['water']['density'])
            w['position']=position; w['velocity']=velocity; w['hydrodynamics']=diagnostics
            velocity=np.asarray(velocity)
            w['distance_travelled']+=float(np.linalg.norm(np.asarray(position)-old))
            if np.linalg.norm(desired[:2])>.04 and not self.manual_jaw:
                heading=math.atan2(desired[1],desired[0]); error=(heading-w['yaw']+math.pi)%(2*math.pi)-math.pi
                w['yaw']+=max(-1.5*dt,min(1.5*dt,error))
            self._sync()
            just_dropped=False
            if self.fragment_held() and self.fsm_state=='NAVIGATE_TO_RECIPIENT' and np.linalg.norm(desired)>.04:
                self.carry_elapsed+=dt
                if self.inject_drop and not self.drop_done and self.carry_elapsed>=2.3:
                    just_dropped=True
                    self.drop_done=True; self.active_fragment['stage']='dropped'
                    self.worker['carrying']=False; self.worker['gripper_open']=1.
                    self.drop_velocity=velocity.tolist()
                    self.worker['state']='FRAGMENT_LOST'
                    self.audit.append({'time':self.sim.time,'event':'fragment_lost','fragment_id':self.active_fragment['id'],
                                       'cause':'injected grip-slip perturbation','force_n':0.})
                    self.sim._event('loss','Grip force lost — recover this same fragment')
            if self.active_fragment and self.active_fragment['stage']=='dropped' and not just_dropped:
                f=self.active_fragment
                from .reef_landscape import _foundation_height
                floor=_foundation_height(f['position'][0],f['position'][1],self.sim.config,self.sim.snapshot())+.001
                f['position'],self.drop_velocity=dropped_step(f['position'],self.drop_velocity,flow,dt,floor=floor)
                f['base_world']=f['position'][:]
            self._record()
    def _move_body(self,point,state,yaw=None):
        self.worker['state']=state; self.manual_jaw=False
        self.locked=False
        for _ in range(1600):
            error=np.asarray(point)-self.worker['position']
            if np.linalg.norm(error)<.025: break
            velocity=1.8*error; speed=np.linalg.norm(velocity)
            self.command=velocity*min(1.,.65/max(speed,1e-9)); self.wait(.05)
        else: raise RuntimeError('adapter approach navigation timed out')
        self.command[:]=0; self.wait(.3)
        if yaw is not None:
            self._face(yaw)
    def _face(self,yaw):
        for _ in range(120):
            error=(yaw-self.worker['yaw']+math.pi)%(2*math.pi)-math.pi
            if abs(error)<.003: break
            self.worker['yaw']+=max(-.06,min(.06,error)); self.wait(.05)
    def _arm(self,state,end,duration,opening=None,*,track_stowed=False):
        self.command[:]=0; self.locked=True; self.manual_jaw=True
        start=self.worker['gripper_world'][:]; first=self.worker['gripper_open']
        self.worker['state']=state
        steps=max(1,round(duration/.05))
        for i in range(steps):
            t=(i+1)/steps; blend=t*t*(3-2*t)
            self.worker['phase_progress']=t
            # The hull keeps moving under current during retraction. End at
            # its present stow location instead of a stale pre-retraction pose.
            target=self.sim._stowed_gripper(self.worker) if track_stowed else end
            self.worker['gripper_world']=[start[k]*(1-blend)+target[k]*blend for k in range(3)]
            if opening is not None: self.worker['gripper_open']=first*(1-blend)+opening*blend
            self.wait(.05)
    def _colony(self,entry):
        cid=getattr(entry,'cluster_id',None)
        if cid in self.sim._truth_by_id: return self.sim._truth_by_id[cid]
        return min(self.sim.corals,key=lambda c:distance(c['position'][:2],entry.position_world[:2]))
    def _scan(self,coral,counterpart,role):
        from .uv_detection import scan_plan,evaluate_detection
        plan=scan_plan(coral,self.sim.config)
        self.worker.update(scan_target_id=coral['id'],scan_target_world=plan['target_world'],detection_status='pending')
        self._move_body(plan['body_target'],'NAVIGATE_TO_SCAN_RECIPIENT' if role=='recipient' else 'NAVIGATE_TO_DONOR',plan['yaw'])
        self.worker['state']='SCAN_RECIPIENT' if role=='recipient' else 'SCAN_DONOR'
        for i in range(60): self.worker['phase_progress']=(i+1)/60; self.wait(.05)
        obs=lambda c:dict(c,confidence=.95)
        receipt=evaluate_detection(coral,counterpart,self.worker,self.sim.config,role=role,timestamp=self.sim.time,
            observed=obs(coral),counterpart_observed=obs(counterpart),blockers=self.sim.corals+self.sim.obstacles,
            fragment=self.active_fragment)
        self.worker['uv_detection']=receipt; self.worker['detection_status']=receipt['status'] if 'status' in receipt else ('accepted' if receipt.get('accepted') else 'rejected')
        self.sim._detection_history.append(receipt); self.audit.append(dict(receipt,event='uv_'+role))
        self.wait(.8)
        return {'allowed':receipt.get('accepted',receipt.get('status')=='accepted'),'sensor_backend':'synthetic optical proxy',**receipt}
    def can_return_fragment(self,source):
        # Reattaching a cut branch to a living donor is not a validated return
        # fixture. The team FSM stops and retains it rather than inventing one.
        return False
    def prepare_pair(self,recipient,source):
        if source is None or source.slot not in self.sim._truth_by_id:
            return {'allowed':False,'reason':'living donor source unavailable'}
        target=self._colony(recipient)
        if self.fragment_held():
            f=self.active_fragment
            approved=any(r.get('accepted') and r.get('role')=='recipient' and r.get('coral_id')==target['id'] for r in self.sim._detection_history)
            compatible=(f['donor_id']==source.slot and f.get('genet_id')==target.get('genet_id') and target['health']=='bleached_alive')
            if not approved or not compatible:
                return {'allowed':False,'reason':'carried fragment requires a compatible pre-harvest-approved recipient','fragment_id':f['id']}
            self.recipient=target; f['target_id']=target['id']; self.worker['task_id']=target['id']
            return {'allowed':True,'reason':'retain original carried fragment and prior UV approval','fragment_id':f['id']}
        available=[f for f in self.sim.fragments if f['donor_id']==source.slot and f['stage']=='attached_to_donor']
        if not available:
            return {'allowed':False,'reason':'source inventory does not contain a harvestable fragment'}
        self.recipient=target; self.source=self.sim._truth_by_id[source.slot]
        self.active_fragment=available[0]
        f=self.active_fragment
        self.worker.update(task_id=self.recipient['id'],donor_id=source.slot,fragment_id=f['id'],fragment_index=f['index'])
        f['target_id']=self.recipient['id']; f['reserved_by']=self.worker['id']
        return self._scan(self.recipient,self.source,'recipient')
    def inspect_donor(self,source,recipient):
        result=self._scan(self.source,self.recipient,'donor')
        if result['allowed']:
            pose=self.navigation_pose(source,purpose='donor')
            self._move_body(pose.position,'NAVIGATE_TO_PICKUP',self._donor_yaw())
        return result
    def _donor_yaw(self):
        f=self.active_fragment; c=self.source
        return math.atan2(c['position'][1]-f['source_position'][1],c['position'][0]-f['source_position'][0])
    def navigation_pose(self,entry,purpose='recipient'):
        if purpose=='donor':
            f=self.active_fragment; yaw=self._donor_yaw(); point=f['source_position']
            return Pose((point[0]-.36*math.cos(yaw),point[1]-.36*math.sin(yaw),max(.7,point[2]+.51)))
        coral=self._colony(entry); p=coral['planting_point']; n=coral['contact_normal']
        return Pose((p[0]+.38*n[0],p[1]+.38*n[1],max(.70,p[2]+.51)))
    def solve_ik(self,pose):
        # The adapter uses a verified two-link workspace; donor target is a
        # colony centre, so use the chosen branch's actual grasp coordinate.
        if self.active_fragment and self.active_fragment['stage']=='attached_to_donor':
            f=self.active_fragment; off=self._grasp_offset(f); target=[f['position'][i]+off[i] for i in range(3)]
        else: target=pose.position
        return distance(self.worker['position'],target)<.85
    def attach_fragment(self,cluster_id):
        if not self.active_fragment or cluster_id!=self.source['id']: raise ValueError('wrong living donor')
        f=self.active_fragment; off=self._grasp_offset(f)
        grip=[f['position'][i]+off[i] for i in range(3)]
        f['_grip_heading_offset']=self.worker['yaw']-f['yaw']
        self.worker['grasp_radius']=f.get('grasp_radius',.025)
        self._arm('APPROACH_FRAGMENT',grip,2.5,1.)
        self._arm('CLOSE_GRIPPER',grip,1.2,0.)
        self._arm('DETACH_FRAGMENT',grip,1.)
        f['stage']='carried'; self.worker['carrying']=True
        self.source['harvested_fragments']+=1
        self.audit.append({'event':'harvest','time':self.sim.time,'fragment_id':f['id'],'source':'living_reef'})
        self._arm('RETRACT_FRAGMENT',self.sim._stowed_gripper(self.worker),2.,track_stowed=True)
        self.manual_jaw=False
    def recover_lost_fragment(self,fragment_id,recipient_id):
        f=self.active_fragment
        if f is None or f['id']!=fragment_id or f['stage']!='dropped' or f['target_id']!=recipient_id: return {'recovered':False,'fragment_id':fragment_id}
        self.command[:]=0; self.worker['state']='FRAGMENT_LOST'; self.wait(3.)
        point=f['position'][:]; yaw=self.worker['yaw']
        self._move_body([point[0]-.32*math.cos(yaw),point[1]-.32*math.sin(yaw),.64],'RECOVER_FRAGMENT',yaw)
        off=self._grasp_offset(f); grip=[f['position'][i]+off[i] for i in range(3)]
        self._arm('RECOVERY_APPROACH',grip,2.4,1.)
        self._arm('RECOVERY_GRASP',grip,1.4,0.)
        f['stage']='carried'; self.worker['carrying']=True
        self._arm('RECOVERY_LIFT',self.sim._stowed_gripper(self.worker),2.,track_stowed=True)
        self.manual_jaw=False; self.locked=False
        ev={'recovered':True,'fragment_id':f['id'],'time':self.sim.time,'grip_force_n':.35,'same_fragment':True}
        self.audit.append(dict(ev,event='recovered')); self.sim._event('recovery','Same fragment regrasped — resume transfer')
        return ev
    def contact_candidate(self,entry):
        coral=self._colony(entry); f=self.active_fragment
        from .scanned_fragment import split_scanned_donor
        donor=self.source
        part=split_scanned_donor(donor['radius'],donor['height'],f['source_mesh_seed'],slots=donor.get('scanned_partition_slots',donor['donor_capacity']),detail=f.get('source_mesh_detail','hero'))['fragments'][f['source_slot']]
        from .natural_contact import central_scanned_contact
        chosen=central_scanned_contact(coral,part,coral['contact_fixture']['source_mesh_seed'],detail=coral['contact_fixture'].get('source_mesh_detail','hero'))
        points=np.asarray(part['mesh']['points']); normal=np.asarray(chosen['normal'])
        yaw=chosen['yaw']; index=chosen['fragment_vertex']; base=np.asarray(chosen['base'])
        coral.update(planting_point=base.tolist(),contact_base=base.tolist(),contact_point=chosen['point'],contact_normal=chosen['normal'])
        coral['contact_fixture'].update(source_triangle_index=chosen['triangle_index'],
            contact_triangle_world=chosen['triangle'],contact_patch_triangle_indices=chosen['patch_triangles'],
            support_point=chosen['support_point'],natural_fragment_contact_local=points[index].tolist(),
            natural_fragment_contact_index=index,natural_fragment_contact_yaw=yaw,
            contact_area_proxy_m2=chosen['contact_area_proxy_m2'],contact_vertices=chosen['contact_vertices'],
            minimum_surface_separation_m=chosen['minimum_surface_separation_m'],
            radial_fraction=chosen['radial_fraction'],selection_method=chosen['method'])
        self.placement_base=base.tolist(); self.placement_yaw=yaw
        old_yaw=f['yaw']; f['yaw']=yaw
        grip=base+np.asarray(self._grasp_offset(f)); f['yaw']=old_yaw
        # Reposition the hull around the newly selected central branch before
        # extending the arm; the old outer-branch staging pose is not reused.
        heading=math.atan2(-normal[1],-normal[0])
        self._move_body([base[0]+.38*normal[0],base[1]+.38*normal[1],max(.70,base[2]+.51)],
                        'NAVIGATE_TO_SITE',heading)
        self.worker['state']='ORIENT_FRAGMENT'; self.manual_jaw=True
        candidate=GraftCandidate(tuple(grip),(0.,0.,0.,1.),tuple(normal),len(coral['contact_fixture']['contact_patch_triangle_indices']),float(normal[2]))
        return candidate,{'method':'actual scanned fragment tissue / existing recipient triangle','triangle':coral['contact_fixture']['source_triangle_index'],'fragment_vertex':index}
    def detach_fragment(self,at_pose):
        f=self.active_fragment
        initial_yaw=f['yaw']; delta=(self.placement_yaw-initial_yaw+math.pi)%(2*math.pi)-math.pi
        self.worker['state']='ORIENT_FRAGMENT'; self.manual_jaw=True
        for i in range(40):
            t=(i+1)/40; f['yaw']=initial_yaw+delta*t*t*(3-2*t); self.wait(.05)
        f['yaw']=self.placement_yaw
        final_grip=np.asarray(at_pose.position)
        preseat=final_grip+np.asarray(self.recipient['contact_normal'])*.004+np.array([0.,0.,.025])
        self._arm('LOWER_FRAGMENT',preseat.tolist(),3.)
        self._arm('SECURE_FRAGMENT',final_grip.tolist(),3.)
        # The carried pose has already reached contact; changing ownership
        # must not teleport the cutting onto a separately computed anchor.
        if distance(f['position'],self.placement_base)>1e-7:
            raise RuntimeError('Seating did not reach the planned contact continuously')
        f['stage']='placed'; f['base_world']=f['position'][:]
        self.worker['carrying']=False
        c=self.recipient
        c.update(fragment_attached=True,attachment_position=f['position'][:],fragment_id=f['id'],source_donor_id=f['donor_id'])
        self._arm('OPEN_GRIPPER',list(at_pose.position),1.5,1.)
        self._arm('RETRACT_GRIPPER',self.sim._stowed_gripper(self.worker),2.,track_stowed=True)
        self.manual_jaw=False
        self.audit.append({'event':'placed','time':self.sim.time,'fragment_id':f['id'],'contact':'natural scanned tissue'})
    def placement_verifier(self,pose):
        f=self.active_fragment; base=np.asarray(f['position']); n=np.asarray(self.recipient['contact_normal'])
        from .natural_contact import closest_point_on_triangle
        fixture=self.recipient['contact_fixture']
        local=np.asarray(fixture['natural_fragment_contact_local'])
        co,si=math.cos(f['yaw']),math.sin(f['yaw'])
        contact_offset=np.array([co*local[0]-si*local[1],si*local[0]+co*local[1],local[2]])
        max_contact_gap=0.
        response=push_response(); self.worker['state']='PUSH_TEST'
        self.manual_jaw=True
        contact=base+np.asarray(self._grasp_offset(f))
        self._arm('PUSH_APPROACH',(contact+n*.015).tolist(),1.2)
        self.worker['state']='PUSH_TEST'
        for i in range(0,len(response['samples']),5):
            row=response['samples'][i]
            f['position']=(base+n*row['displacement_m']).tolist(); f['base_world']=f['position'][:]
            self.worker['gripper_world']=(contact+n*(.015+row['displacement_m'])).tolist()
            tissue=np.asarray(f['position'])+contact_offset
            nearest=closest_point_on_triangle(tissue,*fixture['contact_triangle_world'])
            max_contact_gap=max(max_contact_gap,float(np.linalg.norm(tissue-nearest)))
            self.worker['push_force_n']=row['force_n']; self.wait(.05)
        f['position']=base.tolist(); f['base_world']=base.tolist()
        report={k:v for k,v in response.items() if k!='samples'}
        report.update(contact=max_contact_gap<=fixture['contact_tolerance_m'],max_contact_gap_m=max_contact_gap,fragment_id=f['id'],time=self.sim.time)
        self.push_tests.append(report)
        self._arm('VERIFY_ATTACHMENT',self.sim._stowed_gripper(self.worker),2.,track_stowed=True)
        self.worker['push_force_n']=0.; self.manual_jaw=False
        if report['stable'] and report['contact']:
            self.recipient['task_status']='verified'
            self.sim.observations[self.recipient['id']]['task_status']='verified'
        self.audit.append(dict(report,event='push_test')); self.wait(1.)
        return report
    def get_hull_rgbd(self):
        # Explicit offline sensor fixture: the mission map was supplied before
        # this dive. No empty synthetic image is passed off as real inference.
        rgb=np.full((96,128,3),(10,55,64),dtype=np.uint8)
        depth=np.full((96,128),self.worker['position'][2],dtype=np.float32)
        transform=np.diag([1.,-1.,-1.,1.])
        return RGBDFrame(rgb,depth,(90.,90.,64.,48.),transform)
    def get_wrist_rgbd(self): return self.get_hull_rgbd()
    def get_uv_frame(self): return np.zeros((96,128,3),dtype=np.uint8)
