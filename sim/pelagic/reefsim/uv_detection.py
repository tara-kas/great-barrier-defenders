"""Shared UV preflight geometry and synthetic optical/registry approval.

UV illuminates a candidate before harvesting or placement. Fluorescence is
one simulated signal; health, species and clonal identity remain separately
known scenario observations. This is not genetic inference from RGB colour.
"""
from __future__ import annotations

import math

from .inspection import GROUPS, HEALTH_STATES, appearance_profile, beam_exposure, inspection_response


WRIST_LIGHT_OFFSET = (.13, -.20, .055)
SCAN_STATES = frozenset({"SCAN_RECIPIENT", "SCAN_DONOR"})
SCAN_TRANSIT_STATES = frozenset({"NAVIGATE_TO_SCAN_RECIPIENT", "NAVIGATE_TO_DONOR"})


def _rotate(offset, yaw):
    cosine, sine = math.cos(yaw), math.sin(yaw)
    return [cosine*offset[0]-sine*offset[1], sine*offset[0]+cosine*offset[1], offset[2]]


def scan_plan(coral, config):
    """Return a broad-beam standoff with the empty wrist safely stowed.

    The jaw remains at body-local (.34,0,-.32); the source is its real wrist
    offset, so the arm never stretches out to fabricate a distant light pose.
    """
    options = config.get("inspection", {})
    target = [coral["position"][0], coral["position"][1],
              coral["position"][2] + coral["height"]*.5]
    outward = coral.get("contact_normal") or (0., -1., 0.)
    xy_length = math.hypot(outward[0], outward[1])
    outward = (outward[0]/xy_length, outward[1]/xy_length) if xy_length > 1e-8 else (0., -1.)
    margin_x = config["world"]["width"]*.5 - .35
    margin_y = config["world"]["length"]*.5 - .35
    x = max(-margin_x, min(margin_x, target[0]+outward[0]*.75))
    y = max(-margin_y, min(margin_y, target[1]+outward[1]*.75))
    yaw = math.atan2(target[1]-y, target[0]-x)
    source_offset = _rotate((.34+WRIST_LIGHT_OFFSET[0], WRIST_LIGHT_OFFSET[1],
                             -.32+WRIST_LIGHT_OFFSET[2]), yaw)
    horizontal = math.hypot(x+source_offset[0]-target[0], y+source_offset[1]-target[1])
    standoff = float(options.get("detection_standoff", 1.1))
    source_height = math.sqrt(max(.09, standoff*standoff-horizontal*horizontal))
    z = min(config["world"]["depth"]-.5, max(1.35, target[2]+source_height-source_offset[2]))
    actual_distance = math.hypot(horizontal, z+source_offset[2]-target[2])
    return {"body_target": [x, y, z], "yaw": yaw, "target_world": target,
            "standoff_m": actual_distance,
            "coverage_radius_m": actual_distance*math.tan(math.radians(options.get("half_angle_degrees", 50.)))}


def scan_light_pose(worker, target_world=None):
    """Actual world source/direction shared by core and scene during a scan."""
    target = target_world if target_world is not None else worker.get("scan_target_world")
    if target is None:
        raise ValueError("A detection target is required for the scan light")
    jaw = worker.get("gripper_world")
    if jaw is None:
        offset = _rotate((.34, 0., -.32), worker["yaw"])
        jaw = [worker["position"][i]+offset[i] for i in range(3)]
    offset = _rotate(WRIST_LIGHT_OFFSET, worker["yaw"]+worker.get("wrist_yaw",0.))
    origin = [jaw[i]+offset[i] for i in range(3)]
    delta = [target[i]-origin[i] for i in range(3)]
    length = math.hypot(*delta)
    if length < 1e-8:
        raise ValueError("Scan source cannot coincide with its target")
    return {"light_position": origin, "light_direction": [v/length for v in delta],
            "target_world": list(target), "distance_m": length}


def mission_profile(coral, index, seed):
    """Mirror the scene's appearance profile; lineage comes from the registry."""
    profile = appearance_profile(coral["id"], seed, group=GROUPS[index % len(GROUPS)])
    if coral.get("genotype_known") and coral.get("genet_id") in ("R", "G"):
        green = coral["genet_id"] == "G"
        profile.update(group="green" if green else "red", synthetic_genotype=coral["genet_id"],
                       genotype_source=coral["genotype_source"], negative_control=False,
                       pigment_rgb=[.54, .38, .21] if green else [.48, .28, .17],
                       fluorescence_rgb=[.05, 1., .10] if green else [1., .08, .12],
                       fluorescence_gain=.9)
    return profile


def beam_unoccluded(origin, destination, blockers, ignore=()):
    """Same conservative colony/rock visibility rule used by the renderer."""
    delta = [destination[i]-origin[i] for i in range(3)]
    xy2 = delta[0]**2+delta[1]**2
    for item in blockers:
        if item.get("id") in ignore:
            continue
        center = item["position"]
        t = ((center[0]-origin[0])*delta[0]+(center[1]-origin[1])*delta[1])/max(xy2, 1e-8)
        if .04 < t < .96:
            point = [origin[i]+delta[i]*t for i in range(3)]
            if (math.hypot(point[0]-center[0], point[1]-center[1]) < item["radius"]*.85
                    and center[2] < point[2] < center[2]+item["height"]):
                return False
    return True


def evaluate_detection(coral, counterpart, worker, config, *, role, timestamp,
                       observed, counterpart_observed, blockers=(), profile=None, fragment=None):
    """Return a receipt without mutating any biological or mission state."""
    if role not in ("recipient", "donor"):
        raise ValueError("Detection role must be recipient or donor")
    options = config.get("inspection", {})
    pose = scan_light_pose(worker)
    if profile is None:
        index = max(0, int(coral["id"].rsplit("-", 1)[-1])-1)
        profile = mission_profile(coral, index, int(config["seed"]))
    clear = beam_unoccluded(pose["light_position"], pose["target_world"], blockers, {coral["id"]})
    exposure = beam_exposure(pose["target_world"], pose["light_position"], pose["light_direction"],
                             range_m=options.get("range_m", 3.5),
                             half_angle_degrees=options.get("half_angle_degrees", 50.),
                             attenuation=options.get("attenuation", .35)) if clear else 0.
    health = coral["health"]
    response = inspection_response(profile, health if health in HEALTH_STATES else "dead", exposure, "uv")
    expected_health = "bleached_alive" if role == "recipient" else "healthy"
    counterpart_health = "healthy" if role == "recipient" else "bleached_alive"
    reason = "accepted"
    observations = (observed, counterpart_observed)
    if any(not value or value.get("confidence", 0.) < .45 for value in observations):
        reason = "insufficient_observation"
    elif health == "dead" or counterpart["health"] == "dead":
        reason = "dead_coral_excluded"
    elif health != expected_health or observed.get("health") != expected_health:
        reason = "recipient_not_bleached_alive" if role == "recipient" else "donor_not_healthy"
    elif counterpart["health"] != counterpart_health or counterpart_observed.get("health") != counterpart_health:
        reason = "paired_colony_health_invalid"
    elif not all(value.get("genotype_known") and value.get("genet_id")
                 for value in (coral, counterpart, observed, counterpart_observed)):
        reason = "unknown_lineage"
    elif len({value["genet_id"] for value in (coral, counterpart, observed, counterpart_observed)}) != 1:
        reason = "lineage_mismatch"
    elif not coral.get("species") or len({value.get("species") for value in (coral, counterpart, observed, counterpart_observed)}) != 1:
        reason = "species_mismatch"
    elif fragment is not None and (fragment.get("genet_id") != coral["genet_id"]
                                    or fragment.get("source_species") != coral["species"]):
        reason = "fragment_registry_mismatch"
    elif exposure < options.get("min_detection_exposure", .1):
        reason = "insufficient_uv_exposure" if clear else "uv_beam_occluded"
    elif profile.get("negative_control") or max(response["emission_rgb"]) < options.get("min_detection_signal", .015):
        reason = "no_usable_uv_host_signal"
    return {"coral_id": coral["id"], "role": role, "timestamp": float(timestamp), "mode": "uv",
            "exposure": exposure, "signal_rgb": list(response["emission_rgb"]),
            "accepted": reason == "accepted", "reason": reason,
            "known_genet": coral.get("genet_id"), "known_species": coral.get("species"),
            "health": health, "paired_colony_id": counterpart["id"],
            "fragment_id": worker.get("fragment_id"),
            "target_world": pose["target_world"], "light_position": pose["light_position"],
            "light_direction": pose["light_direction"], "standoff_m": pose["distance_m"],
            "coverage_radius_m": pose["distance_m"]*math.tan(math.radians(options.get("half_angle_degrees", 50.))),
            "occluded": not clear, "source": "synthetic_optical_model_and_known_registry",
            "health_inferred_from_fluorescence": False, "genotype_inferred_from_rgb": False}
