"""Configuration shared by the simulator, Isaac adapter and mission preview."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path


DEFAULT_CONFIG = {
    "seed": 26,
    "world": {"width": 10.0, "length": 10.0, "depth": 8.0},
    "water": {"visibility": 3.8, "turbidity": 0.48, "current": [0.10, 0.035, 0.0],
              "density": 1025.0, "attenuation_rgb": [0.65, 0.19, 0.10],
              "backscatter_rgb": [0.025, 0.15, 0.18]},
    "robot": {"mass": 18.0, "displaced_volume": 18.0 / 1025.0,
              "max_speed": 1.05, "max_thrust": 38.0, "radius": 0.28,
              "linear_drag": [10.0, 12.0, 16.0], "quadratic_drag": [5.0, 6.0, 8.0],
              "survey_altitude": 1.65, "working_altitude": 1.05,
              "camera_half_fov_degrees": 58.0, "camera_period": 0.4,
              "attachment_position_tolerance": 0.16,
              "attachment_speed_tolerance": 0.08, "attachment_dwell": 2.0},
    # Legacy nursery overlay is accepted for old configurations but is unused.
    "nursery": {"position": [-3.65, -3.65, 0.65], "inventory": 6},
    "donors": {"fragments_per_colony": 2, "max_fragments": 6},
    "inspection": {"enabled": False, "require_detection": False, "detection_duration": 3.,
                   "detection_standoff": 1.1, "min_detection_exposure": .1,
                   "min_detection_signal": .015},
    "mission": {"planting_sites": 4, "collection_dwell": 1.5, "verification_dwell": 1.0,
                "attachment_method": "limestone_outplant", "genet_assignments": {},
                "approach_duration": 2., "close_duration": 1.1, "detach_duration": .9,
                "retract_duration": 1.7, "lower_duration": 2.4, "secure_duration": 1.,
                "open_duration": 1.3, "retreat_duration": 1.6},
    "regions": [
        {"id": "living", "name": "LIVING DONOR REEF", "center": [-2.6, -2.45, 0.0],
         "radius": 2.0, "health": "healthy", "color": "#6cd4ad", "policy": "donor"},
        {"id": "bleached", "name": "BLEACHED / ALIVE", "center": [2.6, -2.45, 0.0],
         "radius": 1.9, "health": "bleached_alive", "color": "#e7dac3", "policy": "plant"},
        {"id": "restoration", "name": "DEAD REEF", "center": [2.6, 2.45, 0.0],
         "radius": 1.9, "health": "dead", "color": "#77b8ca", "policy": "exclude"},
        {"id": "hazard", "name": "UNSTABLE RUBBLE", "center": [-2.6, 2.45, 0.0],
         "radius": 1.9, "health": "dead", "color": "#dc9674", "policy": "avoid"}
    ],
    "assumptions": {
        "biology": "No growth, fusion, survival or bleaching recovery model. Attachment is an engineering outcome.",
        "assistance": "Healthy donor cuttings are outplanted beside bleached but living colonies only; healthy recipients and dead colonies are excluded. The recipient remains bleached_alive after engineering assistance.",
        "depth": "Ideal geometric depth and exact vehicle localization; optical observations are visibility limited.",
        "dynamics": "Reduced translational hydrodynamics with buoyancy, current-relative drag and bounded thrust; no CFD or added mass.",
        "manipulation": "Explicit timed jaw closure, detachment, continuous carry, seating, opening and withdrawal; force-contact and adhesive chemistry are abstracted.",
        "communication": "Reliable shared map; no acoustic channel simulation.",
        "substrate": "Pre-existing stable limestone mounts beside bleached but living colonies support abstract outplanting assistance. Dead colonies are excluded; attachment does not model bleaching recovery, roots or new colony growth."
    }
}


def _merge(base, updates):
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def load_config(path=None):
    """Load a JSON overlay, retaining defaults for unspecified parameters."""
    result = copy.deepcopy(DEFAULT_CONFIG)
    if isinstance(path, dict):
        result = _merge(result, path)
    elif path is not None:
        with Path(path).open(encoding="utf-8") as handle:
            result = _merge(result, json.load(handle))
    if isinstance(result.get("inspection"), dict) and result["inspection"].get("require_detection"):
        result["inspection"].setdefault("half_angle_degrees", 50.)
        result["inspection"].setdefault("range_m", 3.5)
    validate_config(result)
    return result


def validate_config(config):
    def number(value, name):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        return float(value)

    for group in ("world", "water", "robot", "nursery", "donors", "mission", "inspection"):
        if not isinstance(config.get(group), dict):
            raise ValueError(f"{group} must be an object")
    if number(config["world"]["width"], "world.width") < 8 or number(config["world"]["length"], "world.length") < 8:
        raise ValueError("This reef layout requires world dimensions of at least 8 metres")
    if number(config["world"]["depth"], "world.depth") < 2.5:
        raise ValueError("world.depth must be at least 2.5 metres")
    if not 0.5 <= number(config["water"]["visibility"], "water.visibility") <= 20:
        raise ValueError("visibility must be between 0.5 and 20 metres")
    if not 0 <= number(config["water"]["turbidity"], "water.turbidity") <= 1:
        raise ValueError("turbidity must be between zero and one")
    current = config["water"]["current"]
    if not isinstance(current, (list, tuple)) or len(current) != 3:
        raise ValueError("current must contain three components between -1 and 1 m/s")
    if any(abs(number(value, "water.current")) > 1 for value in current):
        raise ValueError("current must contain three components between -1 and 1 m/s")
    if number(config["water"]["density"], "water.density") <= 0:
        raise ValueError("water.density must be positive")
    for key in ("attenuation_rgb", "backscatter_rgb"):
        values = config["water"][key]
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            raise ValueError(f"water.{key} must contain three numbers")
        if any(number(value, f"water.{key}") < 0 for value in values):
            raise ValueError(f"water.{key} must be non-negative")
    for key in ("mass", "max_speed", "max_thrust", "camera_period", "displaced_volume", "radius",
                "survey_altitude", "working_altitude", "attachment_position_tolerance",
                "attachment_speed_tolerance", "attachment_dwell"):
        if number(config["robot"][key], f"robot.{key}") <= 0:
            raise ValueError(f"robot.{key} must be positive")
    for key in ("linear_drag", "quadratic_drag"):
        values = config["robot"][key]
        if not isinstance(values, (list, tuple)) or len(values) != 3 or any(number(v, f"robot.{key}") < 0 for v in values):
            raise ValueError(f"robot.{key} must contain three non-negative numbers")
    if not 5 <= number(config["robot"]["camera_half_fov_degrees"], "robot.camera_half_fov_degrees") <= 85:
        raise ValueError("camera_half_fov_degrees must be between 5 and 85")
    inventory = number(config["nursery"]["inventory"], "nursery.inventory")
    if inventory < 0 or inventory != int(inventory):
        raise ValueError("nursery.inventory cannot be negative")
    sites = number(config["mission"]["planting_sites"], "mission.planting_sites")
    if sites < 0 or sites > 6 or sites != int(sites):
        raise ValueError("mission.planting_sites must be an integer between zero and six")
    if config["mission"]["attachment_method"] not in ("limestone_outplant", "same_genet_contact"):
        raise ValueError("mission.attachment_method must be limestone_outplant or same_genet_contact")
    genets = config["mission"]["genet_assignments"]
    if not isinstance(genets, dict) or any(not isinstance(key, str) or not key or
            (value is not None and (not isinstance(value, str) or not value.strip()))
            for key, value in genets.items()):
        raise ValueError("mission.genet_assignments must map coral IDs to known lineage strings or null")
    for key in ("fragments_per_colony", "max_fragments"):
        value = number(config["donors"][key], f"donors.{key}")
        if value < 0 or value != int(value) or value > 30:
            raise ValueError(f"donors.{key} must be an integer between zero and 30")
    for key in ("collection_dwell", "verification_dwell", "approach_duration", "close_duration",
                "detach_duration", "retract_duration", "lower_duration", "secure_duration",
                "open_duration", "retreat_duration"):
        if number(config["mission"][key], f"mission.{key}") <= 0:
            raise ValueError(f"mission.{key} must be positive")
    inspection = config["inspection"]
    for key in ("enabled", "require_detection"):
        if not isinstance(inspection[key], bool):
            raise ValueError(f"inspection.{key} must be a boolean")
    if inspection["require_detection"] and not inspection["enabled"]:
        raise ValueError("inspection.require_detection requires inspection.enabled")
    if inspection["require_detection"] and inspection.get("mode", "auto") != "auto":
        raise ValueError("inspection.require_detection requires inspection.mode auto")
    if not .1 <= number(inspection["detection_duration"], "inspection.detection_duration") <= 30:
        raise ValueError("inspection.detection_duration must be between .1 and 30 seconds")
    if not .5 <= number(inspection["detection_standoff"], "inspection.detection_standoff") <= 3:
        raise ValueError("inspection.detection_standoff must be between .5 and 3 metres")
    for key in ("min_detection_exposure", "min_detection_signal"):
        if not 0 < number(inspection[key], f"inspection.{key}") <= 1:
            raise ValueError(f"inspection.{key} must be in (0,1]")
    if "range_m" in inspection and number(inspection["range_m"], "inspection.range_m") <= 0:
        raise ValueError("inspection.range_m must be positive")
    if "half_angle_degrees" in inspection and not 0 < number(inspection["half_angle_degrees"], "inspection.half_angle_degrees") < 85:
        raise ValueError("inspection.half_angle_degrees must be in (0,85)")
    if "attenuation" in inspection and number(inspection["attenuation"], "inspection.attenuation") < 0:
        raise ValueError("inspection.attenuation must be nonnegative")
