"""Detection is a mission prerequisite, never an effect added after harvesting."""
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from reefsim.config import load_config
from reefsim.core import ReefSimulation, distance
from reefsim.uv_detection import mission_profile, scan_plan, scan_light_pose

ROOT = Path(__file__).resolve().parents[1]


def configuration():
    config = load_config(ROOT/'configs/contact_graft.json')
    config['inspection'].update(require_detection=True, half_angle_degrees=50., range_m=3.5)
    return config


def advance(sim, states, limit=250.):
    while sim.time < limit and sim.robots[1]['state'] not in states:
        sim.step(.05)
    return sim.robots[1]


class DetectionTests(unittest.TestCase):
    def test_full_mission_requires_two_fresh_receipts_before_every_harvest(self):
        sim = ReefSimulation(configuration())
        seen = {}
        previous = {f['id']: f['position'][:] for f in sim.fragments}
        while sim.time < 250:
            sim.step(.05)
            worker = sim.robots[1]
            if worker['fragment_id']:
                states = seen.setdefault(worker['fragment_id'], [])
                if not states or states[-1] != worker['state']:
                    states.append(worker['state'])
            if worker['state'].startswith('SCAN_'):
                self.assertFalse(worker['carrying'])
                self.assertEqual(worker['gripper_open'], 1.)
                fragment = sim._fragments_by_id[worker['fragment_id']]
                self.assertEqual(fragment['stage'], 'attached_to_donor')
                shoulder = [worker['position'][0]+.17*math.cos(worker['yaw']),
                            worker['position'][1]+.17*math.sin(worker['yaw']), worker['position'][2]-.12]
                self.assertLess(distance(shoulder,worker['gripper_world']), .72)
            if worker['state'] == 'NAVIGATE_TO_PICKUP':
                self.assertIsNone(worker.get('scan_target_world'))
                self.assertEqual(worker['detection_status'], 'approved')
            for fragment in sim.fragments:
                self.assertLess(distance(fragment['position'], previous[fragment['id']]), .15)
                previous[fragment['id']] = fragment['position'][:]
                if fragment['stage'] in ('grasped', 'carried', 'placed'):
                    evidence = fragment['detection_evidence']
                    self.assertEqual(set(evidence), {'recipient', 'donor'})
                    for role, receipt in evidence.items():
                        self.assertTrue(receipt['accepted'])
                        self.assertEqual(receipt['mode'], 'uv')
                        self.assertIn(receipt, sim._detection_history)
                        self.assertNotEqual(receipt['health'], 'dead')
                        self.assertFalse(receipt['genotype_inferred_from_rgb'])
                        self.assertLessEqual(receipt['timestamp'], fragment['detection_approved_at'])
                    if fragment['stage'] in ('carried','placed'):
                        self.assertLess(fragment['detection_approved_at'], fragment['harvested_at'])
            if worker['state'] == 'COMPLETE':
                break
        snapshot = sim.snapshot()
        self.assertTrue(snapshot['metrics']['mission_complete'])
        self.assertEqual(snapshot['metrics']['verified'],4)
        self.assertEqual(snapshot['metrics']['inventory'],2)
        self.assertEqual(len(snapshot['detection_history']),8)
        self.assertEqual(snapshot['metrics']['collisions'],0)
        for states in seen.values():
            order = ['SCAN_RECIPIENT','SCAN_DONOR','NAVIGATE_TO_PICKUP','APPROACH_FRAGMENT','CLOSE_GRIPPER','DETACH_FRAGMENT']
            indices = [states.index(state) for state in order]
            self.assertEqual(indices, sorted(indices))

    def test_insufficient_exposure_holds_and_preserves_all_donor_stock(self):
        config = configuration(); config['inspection']['range_m'] = .2
        sim = ReefSimulation(config)
        advance(sim, {'DETECTION_REJECTED'})
        self.assertEqual(sim.robots[1]['state'],'DETECTION_REJECTED')
        self.assertEqual(sim._detection_history[-1]['reason'],'insufficient_uv_exposure')
        self.assertTrue(all(f['stage']=='attached_to_donor' for f in sim.fragments))
        self.assertEqual(sum(c['harvested_fragments'] for c in sim.corals),0)
        sim.step(5.)
        self.assertEqual(sim.robots[1]['state'],'DETECTION_REJECTED')
        self.assertEqual(len(sim._detection_history),1)

    def test_negative_donor_signal_rejects_after_recipient_passes(self):
        sim = ReefSimulation(configuration())
        def profile(coral, index, seed):
            value = mission_profile(coral,index,seed)
            if coral['health']=='healthy':
                value.update(negative_control=True,fluorescence_gain=0.)
            return value
        with patch('reefsim.uv_detection.mission_profile',profile):
            advance(sim, {'DETECTION_REJECTED'})
        self.assertEqual([r['accepted'] for r in sim._detection_history],[True,False])
        self.assertEqual(sim._detection_history[-1]['reason'],'no_usable_uv_host_signal')
        self.assertTrue(all(f['stage']=='attached_to_donor' for f in sim.fragments))

    def test_dead_or_mismatched_recipient_is_never_approved(self):
        for field,value,reason in [('health','dead','dead_coral_excluded'),('genet_id','different','lineage_mismatch')]:
            with self.subTest(field=field):
                sim=ReefSimulation(configuration())
                worker=advance(sim, {'SCAN_RECIPIENT'})
                sim._truth_by_id[worker['task_id']][field]=value
                advance(sim, {'DETECTION_REJECTED'})
                self.assertEqual(sim._detection_history[-1]['reason'],reason)
                self.assertTrue(all(f['stage']=='attached_to_donor' for f in sim.fragments))

    def test_approval_is_rechecked_before_grasp_and_hold_keeps_carried_fragment(self):
        for trigger in ('NAVIGATE_TO_PICKUP','NAVIGATE_TO_SITE'):
            with self.subTest(trigger=trigger):
                sim=ReefSimulation(configuration())
                worker=advance(sim, {trigger})
                fragment=sim._fragments_by_id[worker['fragment_id']]
                original=fragment['position'][:]
                sim._truth_by_id[worker['task_id']]['genet_id']='changed'
                sim.step(.05)
                self.assertEqual(worker['state'],'DETECTION_REJECTED')
                self.assertLess(distance(fragment['position'],original),.01)
                if trigger=='NAVIGATE_TO_PICKUP':
                    self.assertEqual(fragment['stage'],'attached_to_donor')
                    self.assertNotIn('harvested_at',fragment)
                else:
                    self.assertTrue(worker['carrying'])
                    self.assertEqual(worker['gripper_open'],0.)
                    self.assertEqual(fragment['stage'],'carried')

    def test_scan_geometry_matches_actual_stowed_wrist_and_has_broad_footprint(self):
        sim=ReefSimulation(configuration())
        for coral in sim.corals:
            if coral['health']=='dead':
                continue
            plan=scan_plan(coral,sim.config)
            worker={'position':plan['body_target'],'yaw':plan['yaw']}
            worker['gripper_world']=sim._stowed_gripper(worker)
            pose=scan_light_pose(worker,plan['target_world'])
            self.assertAlmostEqual(pose['distance_m'],plan['standoff_m'])
            self.assertGreater(plan['coverage_radius_m'],1.2)
            self.assertAlmostEqual(sum(v*v for v in pose['light_direction']),1.)

    def test_detection_config_rejects_incoherent_lights_and_nonfinite_thresholds(self):
        for overrides in ({'enabled':False},{'mode':'white'},{'mode':'off'},{'mode':'blue'},{'mode':'uv'},
                          {'detection_duration':0},{'detection_standoff':float('nan')},
                          {'min_detection_exposure':0},{'half_angle_degrees':90}):
            with self.subTest(overrides=overrides):
                config=configuration();config['inspection'].update(overrides)
                with self.assertRaises(ValueError):load_config(config)
        self.assertFalse(load_config()['inspection']['require_detection'])


if __name__=='__main__':
    unittest.main()
