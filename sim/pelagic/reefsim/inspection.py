"""Deterministic coral appearance and local inspection-light response.

This is an RGB demonstration model, not a spectral renderer or genetic assay.
Purple/blue chromoprotein pigmentation is not the same as fluorescence. The
violet group deliberately provides a healthy, nonfluorescent negative control;
the other groups emit illustrative cyan, green/yellow or orange/red signals.
The white-light pigment and host fluorescence palettes are separate.

``synthetic_genotype`` is a known scenario tag, independently assigned from the
appearance group. Neither appearance nor fluorescence estimates a genotype.
Bleached living tissue retains/enhances host signal in this scenario. A zero
host signal on dead coral is an explicit demo assumption: it does not imply
that real dead skeletons, associated organisms or algae never fluoresce.

Blue (450 nm) and UV (365 nm) modes name an excitation source. Their returned
emission is an illustrative *visible* RGB proxy, without measured spectra,
camera filters, quantum yield or calibrated radiometry. UV itself is invisible.
All functions are standard-library-only and make no network requests.
"""
from __future__ import annotations

import hashlib
import math


GROUPS = ("violet", "blue", "yellow", "red", "pink")
HEALTH_STATES = ("healthy", "bleached_alive", "dead")
MODES = ("off", "white", "blue", "uv")
_UV_SCAN_STATES = ("NAVIGATE_TO_SCAN_RECIPIENT", "SCAN_RECIPIENT",
                   "NAVIGATE_TO_DONOR", "SCAN_DONOR")

# These are independent illustrative pigment and emission choices, not a
# mapping from a visible colour to a real species, protein or genotype.
_PALETTES = {
    "violet": ((.43, .16, .65), (0., 0., 0.), 0.),
    "blue": ((.13, .30, .72), (.025, .80, 1.), .88),
    "yellow": ((.78, .58, .08), (.58, 1., .04), .92),
    "red": ((.66, .13, .08), (1., .20, .025), .78),
    "pink": ((.72, .26, .44), (1., .07, .16), .84),
}


def _finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _vector(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain three finite numbers")
    return tuple(_finite_number(component, name) for component in value)


def auto_inspection_mode(worker_state, carrying=False):
    """Use UV only for explicit pre-manipulation search/scan phases.

    Any truthy carrying flag forces white light, including while navigating.
    Pickup, attachment and verification remain white; unknown/future states
    also fall back to white rather than accidentally enabling excitation.
    The legacy ``APPROACH_FRAGMENT`` state is manipulation, not a scan.
    """
    return "uv" if not carrying and worker_state in _UV_SCAN_STATES else "white"


def beam_footprint_radius(distance_m, half_angle_degrees):
    """Radius of a conical beam on a perpendicular plane, in metres.

    ``distance_m`` is axial distance from the source, not slant range to the
    cone edge. This geometric footprint does not apply attenuation, occlusion
    or the separately configured light range. For a 50° half angle at 1.1 m,
    its radius is about 1.31 m (2.62 m diameter).
    """
    distance_m = _finite_number(distance_m, "distance_m")
    half_angle_degrees = _finite_number(half_angle_degrees, "half_angle_degrees")
    if distance_m < 0 or not 0 < half_angle_degrees < 90:
        raise ValueError("distance must be nonnegative and half angle in (0,90)")
    radius = distance_m * math.tan(math.radians(half_angle_degrees))
    if not math.isfinite(radius):
        raise ValueError("beam footprint radius exceeds the finite numeric range")
    return radius


def appearance_profile(coral_id, seed=26, group=None):
    """Return independent mutable metadata for one known donor/colony identity.

    For an attached, carried or planted fragment, pass its ``donor_id`` rather
    than its fragment ID so it preserves the donor's appearance and lineage.
    ``group`` optionally fixes a colour for a deliberate comparison case.
    """
    if not isinstance(coral_id, str) or not coral_id:
        raise ValueError("coral_id must be a nonempty string")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    digest = hashlib.sha256(f"pelagic-inspection:{seed}:{coral_id}".encode()).digest()
    if group is None:
        group = GROUPS[digest[0] % len(GROUPS)]
    if group not in GROUPS:
        raise ValueError(f"group must be one of {GROUPS}")
    pigment, emission, gain = _PALETTES[group]
    # Separate hash byte: colour is intentionally not a unique genetic key.
    lineage = f"SIM-G{1 + digest[7] % 4:02d}"
    return {
        "coral_id": coral_id,
        "group": group,
        "pigment_rgb": list(pigment),
        "fluorescence_rgb": list(emission),
        "fluorescence_gain": gain,
        "synthetic_genotype": lineage,
        "genotype_source": "known synthetic scenario tag; not inferred from colour",
        "interpretation": "illustrative pigment/host-fluorescence phenotype",
        "negative_control": group == "violet",
    }


def beam_exposure(position, light_position, light_direction, *, range_m=2.5,
                  half_angle_degrees=28., attenuation=.35):
    """Return local beam illumination in [0,1], with smooth cone/range edges.

    There is no global glow: points behind/outside the cone or beyond range
    receive zero exposure. Direction is normalized internally. This function
    does not trace occluders; a caller can multiply by independently computed
    visibility or pass zero for an occluded surface. ``attenuation`` is a
    phenomenological inverse-metre factor, not wavelength-calibrated water.
    """
    position, origin = _vector(position, "position"), _vector(light_position, "light_position")
    direction = _vector(light_direction, "light_direction")
    range_m = _finite_number(range_m, "range_m")
    half_angle_degrees = _finite_number(half_angle_degrees, "half_angle_degrees")
    attenuation = _finite_number(attenuation, "attenuation")
    if range_m <= 0 or not 0 < half_angle_degrees < 90 or attenuation < 0:
        raise ValueError("range must be positive, half angle in (0,90), attenuation nonnegative")
    norm = math.hypot(*direction)
    if norm < 1e-12:
        raise ValueError("light_direction must have nonzero length")
    delta = tuple(position[i] - origin[i] for i in range(3))
    distance = math.hypot(*delta)
    if distance >= range_m:
        return 0.
    if distance < 1e-12:
        return 1.
    cosine = sum((delta[i] / distance) * (direction[i] / norm) for i in range(3))
    outer = math.cos(math.radians(half_angle_degrees))
    inner = math.cos(math.radians(half_angle_degrees * .70))
    angular = max(0., min(1., (cosine - outer) / (inner - outer)))
    angular = angular * angular * (3. - 2. * angular)
    # A smooth finite falloff avoids an abrupt disappearance at range_m.
    taper = max(0., 1. - (distance / range_m) ** 2) ** 2
    return angular * taper * math.exp(-attenuation * distance)


def inspection_response(profile, health, exposure, mode="white"):
    """Return RGB appearance while preserving independent biological state.

    White/off modes produce zero host emission. The healthy violet negative
    control remains nonfluorescent in every mode. A bright bleached specimen
    remains bleached; a dark healthy specimen remains healthy. A renderer can
    apply its own exposure/intensity to ``emission_rgb`` without changing these
    semantic fields. ``eligible_recipient`` describes health only; the planner
    must still enforce region, observation, substrate and reservation rules.
    """
    if health not in HEALTH_STATES:
        raise ValueError(f"health must be one of {HEALTH_STATES}")
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    exposure = _finite_number(exposure, "exposure")
    if not 0 <= exposure <= 1:
        raise ValueError("exposure must be in [0,1]")
    pigment = _vector(profile["pigment_rgb"], "pigment_rgb")
    emission = _vector(profile["fluorescence_rgb"], "fluorescence_rgb")
    gain = _finite_number(profile["fluorescence_gain"], "fluorescence_gain")
    if gain < 0 or any(not 0 <= v <= 1 for v in pigment + emission):
        raise ValueError("profile colours must be in [0,1] and gain nonnegative")
    if health == "bleached_alive":
        pigment = (.84, .81, .70)
    elif health == "dead":
        pigment = (.23, .27, .18)
    host_factor = {"healthy": .78, "bleached_alive": 1.10, "dead": 0.}[health]
    mode_factor = {"off": 0., "white": 0., "blue": 1., "uv": .85}[mode]
    strength = exposure * gain * host_factor * mode_factor
    return {
        "group": profile["group"],
        "synthetic_genotype": profile["synthetic_genotype"],
        "health": health,
        "eligible_recipient": health == "bleached_alive",
        "pigment_rgb": list(pigment),
        "emission_rgb": [min(1., component * strength) for component in emission],
        "exposure": exposure,
        "mode": mode,
        "excitation_nm": {"off": None, "white": None, "blue": 450, "uv": 365}[mode],
        "signal_kind": "illustrative visible host-fluorescence proxy",
        "health_inferred_from_signal": False,
    }


def showcase_profiles(seed=26):
    """Fifteen labelled records covering all 3 health states × 5 colour groups.

    Each colour is repeated across health states with the same known synthetic
    profile. This makes it possible to compare bleaching effects without
    accidentally changing the selected colour/lineage between examples.
    """
    cases = []
    for row, health in enumerate(HEALTH_STATES):
        for column, group in enumerate(GROUPS):
            profile = appearance_profile(f"showcase-{group}", seed, group=group)
            cases.append({"id": f"inspection-{health}-{group}", "health": health,
                          "row": row, "column": column, "profile": profile})
    return cases
