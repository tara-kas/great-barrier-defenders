"""Read-only checks on the authored USD arm and gripper geometry.

Call ``check_linkage(scene, snapshot)`` after ``scene.update(snapshot)``.
The audit reads actual world transforms, primitive dimensions and cylinder
endpoints. It does not invoke the renderer's IK or gripper layout functions.
No rendering, physics stepping or USD mutation is performed.
"""
from __future__ import annotations

import math


def check_linkage(scene, snapshot):
    from pxr import Gf, Usd, UsdGeom

    stage = scene.stage
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    tolerance = 2e-5

    def prim(path):
        result = stage.GetPrimAtPath(path)
        assert result and result.IsValid(), f"Missing arm linkage geometry: {path}"
        assert UsdGeom.Imageable(result).ComputeVisibility() != UsdGeom.Tokens.invisible, f"Hidden arm linkage: {path}"
        return result

    def matrix(path):
        return cache.GetLocalToWorldTransform(prim(path))

    def center(path):
        return matrix(path).Transform(Gf.Vec3d(0., 0., 0.))

    def endpoints(path, schema):
        shape = schema(prim(path))
        assert shape, f"Unexpected linkage primitive type: {path}"
        height = float(shape.GetHeightAttr().Get())
        axis = str(shape.GetAxisAttr().Get())
        dimension = {"X": 0, "Y": 1, "Z": 2}[axis.upper()]
        result = []
        for side in (-1., 1.):
            point = [0., 0., 0.]
            point[dimension] = side * height / 2
            result.append(matrix(path).Transform(Gf.Vec3d(*point)))
        return result

    def cube_gap(point, path):
        """Actual world distance to this oriented/scaled USD cube volume."""
        cube = UsdGeom.Cube(prim(path))
        assert cube, f"Expected cube at {path}"
        half = float(cube.GetSizeAttr().Get()) / 2
        transform = matrix(path)
        local = transform.GetInverse().Transform(point)
        closest = Gf.Vec3d(*(max(-half, min(half, float(v))) for v in local))
        return (point-transform.Transform(closest)).GetLength()

    def ordered_ends(path, expected_start, expected_end):
        ends = endpoints(path, UsdGeom.Cylinder)
        if (ends[1]-expected_start).GetLength() < (ends[0]-expected_start).GetLength():
            ends.reverse()
        errors = [(ends[0]-expected_start).GetLength(), (ends[1]-expected_end).GetLength()]
        assert max(errors) <= tolerance, f"Disconnected {path}: endpoint errors {errors}"
        return ends, errors

    roots = stage.GetPrimAtPath("/World/Robots")
    assert roots and roots.IsValid(), "Missing robot geometry scope"
    lookup = {str(root.GetCustomDataByKey("reefsim:robot_id")): root.GetPath() for root in roots.GetChildren()}
    records = []
    for robot in snapshot.get("robots", []):
        identifier = str(robot["id"])
        assert identifier in lookup, f"Missing rendered robot {identifier}"
        root = str(lookup[identifier])
        shoulder, elbow = center(root+"/Shoulder"), center(root+"/Elbow")
        wrist = center(root+"/Gripper/WristKnuckle")
        upper, upper_errors = ordered_ends(root+"/ArmUpper", shoulder, elbow)
        fore, fore_errors = ordered_ends(root+"/ArmFore", elbow, wrist)
        lengths = [(upper[1]-upper[0]).GetLength(), (fore[1]-fore[0]).GetLength()]
        # These are the declared fixed link lengths of this ROV. The audit
        # detects the old visual IK's silent stretching on unreachable poses.
        assert abs(lengths[0]-.38) <= tolerance, f"Upper arm stretched: {identifier}: {lengths[0]}"
        assert abs(lengths[1]-.40) <= tolerance, f"Forearm stretched: {identifier}: {lengths[1]}"
        reach = (wrist-shoulder).GetLength()
        assert abs(lengths[0]-lengths[1])-tolerance <= reach <= sum(lengths)+tolerance
        knuckle_prim = prim(root+"/Gripper/WristKnuckle")
        knuckle_matrix = cache.GetLocalToWorldTransform(knuckle_prim)
        knuckle_radius = float(UsdGeom.Sphere(knuckle_prim).GetRadiusAttr().Get()) * min(
            knuckle_matrix.TransformDir(Gf.Vec3d(*axis)).GetLength()
            for axis in ((1.,0.,0.), (0.,1.,0.), (0.,0.,1.)))
        wrist_palm_gap = cube_gap(wrist, root+"/Gripper/Palm")
        assert wrist_palm_gap <= knuckle_radius+tolerance, f"Wrist misses palm: {identifier}"
        rail_gaps = []
        finger_gaps = []
        for index in range(2):
            rail = endpoints(root+f"/Gripper/Slide{index}", UsdGeom.Cylinder)
            palm_path = root+"/Gripper/Palm"
            carriage_path = root+f"/Gripper/Carriage{index}"
            # Either cylinder orientation is valid; one endpoint must enter
            # the palm and the other must enter the moving finger carriage.
            gap = min(max(cube_gap(rail[0], palm_path), cube_gap(rail[1], carriage_path)),
                      max(cube_gap(rail[1], palm_path), cube_gap(rail[0], carriage_path)))
            assert gap <= tolerance, f"Floating jaw rail: {identifier}/{index}: {gap} m"
            rail_gaps.append(gap)
            finger = endpoints(root+f"/Gripper/Jaw{index}/Finger", UsdGeom.Capsule)
            gap = min(cube_gap(point, carriage_path) for point in finger)
            assert gap <= tolerance, f"Finger disconnected from carriage: {identifier}/{index}: {gap} m"
            finger_gaps.append(gap)
        actual_grasp = center(root+"/Gripper")
        grasp_error = None
        if robot.get("gripper_world") is not None:
            grasp_error = (actual_grasp-Gf.Vec3d(*robot["gripper_world"])).GetLength()
            assert grasp_error <= tolerance, f"Gripper moved off authoritative grasp: {identifier}"
        values = lengths+upper_errors+fore_errors+rail_gaps+finger_gaps+[reach, wrist_palm_gap]
        assert all(math.isfinite(float(v)) for v in values), f"Non-finite linkage: {identifier}"
        records.append({"robot_id": identifier, "state": robot.get("state"),
                        "upper_length_m": lengths[0], "forearm_length_m": lengths[1],
                        "shoulder_wrist_reach_m": reach,
                        "max_link_endpoint_error_m": max(upper_errors+fore_errors),
                        "max_rail_connection_gap_m": max(rail_gaps),
                        "max_finger_connection_gap_m": max(finger_gaps),
                        "wrist_palm_overlap_m": knuckle_radius-wrist_palm_gap,
                        "grasp_pose_error_m": grasp_error})
    assert records, "No robot linkages checked"
    return {"passed": True, "time": float(snapshot.get("time", 0.)), "robots": records,
            "measurement": "actual USD world transforms and primitive dimensions"}


def preflight_linkages(config, snapshots):
    """Check actual authored robots before spending time building the reef."""
    import copy
    from pxr import Usd
    from reefsim.isaac_scene import IsaacReefScene

    options = copy.deepcopy(config)
    options.setdefault('inspection', {})['enabled'] = False
    scene = IsaacReefScene(Usd.Stage.CreateInMemory(), options)
    scene.depth = float(options["world"]["depth"])
    scene._make_materials()
    for index, robot in enumerate(snapshots[0]['robots']):
        scene._make_robot(robot, index)
    def robot_state(snapshot):
        return {'robots': snapshot['robots'], 'time': snapshot['time'],
                'water': snapshot['water'], 'corals': [], 'fragments': []}
    scene._make_cameras(robot_state(snapshots[0]))
    records = []
    for snapshot in snapshots:
        scene.update(robot_state(snapshot))
        records.append(check_linkage(scene, snapshot))
    return {'passed': True, 'checks': records, 'scope': 'isolated actual USD robot geometry before reef construction'}
