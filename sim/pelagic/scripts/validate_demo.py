#!/usr/bin/env python3
"""Validate a completed offline three-camera recording and its mission state."""
import argparse
import json
import subprocess
from fractions import Fraction
from pathlib import Path


MANIPULATION_STATES = {"NAVIGATE_TO_PICKUP", "APPROACH_FRAGMENT", "CLOSE_GRIPPER", "DETACH_FRAGMENT", "RETRACT_FRAGMENT",
                       "NAVIGATE_TO_SITE", "LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER",
                       "RETRACT_GRIPPER", "VERIFY_ATTACHMENT"}
UV_DETECTION_STATES = {"NAVIGATE_TO_SCAN_RECIPIENT", "SCAN_RECIPIENT", "NAVIGATE_TO_DONOR", "SCAN_DONOR"}


def validate_detection_recording(state, manifest):
    """Check recorded illumination before action, separately from attachment."""
    config = state.get("recording", {}).get("inspection_config", {})
    if not config.get("enabled"):
        assert not config.get("require_detection"), "Required detection cannot run with inspection disabled"
        return {"required": False, "enabled": False}
    modes = {entry.get("inspection", {}).get("mode") for entry in manifest if entry.get("inspection")}
    assert {"white", "uv"} <= modes, "Mission video must show UV detection and white-light action"
    assert modes <= {"white", "uv"}, "Automatic mission lighting must use UV detection or white light"
    for entry in manifest:
        phase = entry["worker_state"]
        mode = (entry.get("inspection") or {}).get("mode")
        if phase in MANIPULATION_STATES or entry.get("carrying"):
            assert mode == "white", f"{phase} must use white light, not UV/blue treatment"
        if mode == "uv":
            assert phase in UV_DETECTION_STATES, f"UV belongs before harvest/treatment, not {phase}"
    if not config.get("require_detection"):
        return {"required": False, "enabled": True, "modes": sorted(modes)}
    witnessed = {entry["worker_state"] for entry in manifest}
    assert {"SCAN_RECIPIENT", "SCAN_DONOR"} <= witnessed, "Video omitted pre-action UV scan phases"
    for entry in manifest:
        if entry["worker_state"] in {"SCAN_RECIPIENT", "SCAN_DONOR"}:
            assert (entry.get("inspection") or {}).get("mode") == "uv", "Detection scan must show UV illumination"
    assert state.get("detection_required") is True, "Core mission did not enforce detection"
    history = state.get("detection_history", [])
    approved_fragments = []
    for fragment in state.get("fragments", []):
        if fragment.get("stage") == "attached_to_donor":
            continue
        receipts = fragment.get("detection_evidence", {})
        assert set(receipts) == {"recipient", "donor"}, "Harvested fragment lacks both UV approval receipts"
        approved_at = fragment.get("detection_approved_at")
        harvested_at = fragment.get("harvested_at")
        assert isinstance(approved_at, (int, float)) and isinstance(harvested_at, (int, float)), "Missing approval/harvest times"
        assert approved_at < harvested_at, "UV approval must precede harvest"
        for role, colony_id, paired_id in (("recipient", fragment["target_id"], fragment["donor_id"]),
                                           ("donor", fragment["donor_id"], fragment["target_id"])):
            receipt = receipts[role]
            assert receipt.get("accepted") is True and receipt.get("mode") == "uv", "Harvest used rejected/non-UV evidence"
            assert receipt.get("role") == role and receipt.get("coral_id") == colony_id, "UV evidence targets the wrong colony/role"
            assert receipt.get("fragment_id") == fragment["id"] and receipt.get("paired_colony_id") == paired_id, "UV evidence belongs to another transfer"
            assert receipt in history, "UV approval receipt absent from authoritative history"
            assert receipt.get("timestamp", float("inf")) <= approved_at, "UV evidence was recorded after approval"
            scan_phase = "SCAN_RECIPIENT" if role == "recipient" else "SCAN_DONOR"
            assert any(entry["worker_state"] == scan_phase and entry.get("fragment_id") == fragment["id"]
                       and entry.get("sim_time", float("inf")) <= approved_at for entry in manifest), "Video omitted this fragment's pre-harvest UV scan"
        action_times = [entry["sim_time"] for entry in manifest
                        if entry.get("fragment_id") == fragment["id"] and entry["worker_state"] in MANIPULATION_STATES]
        assert action_times and approved_at <= min(action_times), "Manipulation began before UV approval"
        approved_fragments.append(fragment["id"])
    assert approved_fragments, "No approved transfers witnessed"
    return {"required": True, "enabled": True, "modes": sorted(modes), "approved_fragments": approved_fragments,
            "receipt_count": 2 * len(approved_fragments)}


def validate(directory):
    state = json.loads((directory / "state.json").read_text())
    schedule = json.loads((directory / "schedule.json").read_text())
    recording = state["recording"]
    metrics = state["metrics"]
    assert state["mode"] == "isaac-offline-pip"
    assert recording["server_started"] is False
    assert recording["synchronized_render_products"] is True
    assert set(recording["camera_paths"]) == {"director", "scout", "worker"}
    assert len(set(recording["camera_paths"].values())) == 3, "PiPs must use independent cameras"
    assert metrics["mission_complete"] and metrics["observed"] == metrics["total_corals"] == 24
    assert metrics["verified"] == metrics["attached"] == 4
    assert metrics["duplicate_assignments"] == 0
    planted = [c for c in state["corals"] if c["fragment_attached"]]
    assert all(c["health"] == "bleached_alive" for c in planted), "Planting must not rewrite biological state"
    assert all(not c["fragment_attached"] and c["reserved_by"] is None for c in state["corals"] if c["health"] == "dead"), "Dead coral must be excluded from assistance"
    corals = {c["id"]: c for c in state["corals"]}
    fragments = state["fragments"]
    assert len({f["id"] for f in fragments}) == len(fragments), "Fragment IDs must remain unique"
    placed = [f for f in fragments if f["stage"] == "placed"]
    available = [f for f in fragments if f["stage"] == "attached_to_donor"]
    assert len(placed) == metrics["verified"] == len(planted)
    assert len(available) == metrics["donor_fragments_available"]
    assert len(placed) + len(available) == len(fragments), "No fragment may remain lost/in transit"
    assert len({f["target_id"] for f in placed}) == len(placed), "No duplicate placement target"
    for fragment in placed:
        donor = corals[fragment["donor_id"]]
        target = corals[fragment["target_id"]]
        assert donor["health"] == "healthy", "Fragments must originate in living donor reef"
        assert target["health"] == "bleached_alive" and target["fragment_attached"]
        assert fragment.get("position") == fragment.get("base_world"), "Fragment pose aliases diverged"
        if target.get("contact_fixture"):
            assert target["genotype_known"] and donor["genotype_known"]
            assert target["genet_id"] == donor["genet_id"] == fragment["genet_id"]
            assert target["species"] == donor["species"]
    manifest = json.loads((directory / "manifest.json").read_text())
    witnessed = {entry["worker_state"] for entry in manifest}
    required = {"APPROACH_FRAGMENT", "CLOSE_GRIPPER", "DETACH_FRAGMENT", "RETRACT_FRAGMENT",
                "NAVIGATE_TO_SITE", "LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER",
                "RETRACT_GRIPPER", "VERIFY_ATTACHMENT", "COMPLETE"}
    assert required <= witnessed, f"Video omitted action evidence: {sorted(required - witnessed)}"
    detection = validate_detection_recording(state, manifest)
    for entry in manifest:
        if entry["worker_state"] in ("NAVIGATE_TO_SITE", "LOWER_FRAGMENT", "SECURE_FRAGMENT"):
            assert entry.get("gripper_open", 1) <= .05, "A carried fragment must remain clamped"
    assert "nursery" not in state, "Donor-to-reef movie must not contain a nursery/table supply"
    geometry = json.loads((directory / "geometry-validation.json").read_text())
    assert geometry["passed"] and geometry["geometry_unchanged"]
    assert geometry["no_generated_outplant_or_table"]
    assert geometry["persistent_fragment_count"] == len(fragments) == 6
    assert geometry["checks"] >= 10
    assert geometry["max_fragment_pose_error_m"] < 2e-5
    assert geometry["max_jaw_pose_error_m"] < 2e-5
    assert geometry["mount_min_clearance_m"] >= .55 - 1e-6, "Planting workspace intersects surrounding coral/rock"
    contact_ids = {f["id"] for f in placed if corals[f["target_id"]].get("contact_fixture")}
    if contact_ids:
        assert set(geometry["contact_surface_gaps_m"]) == contact_ids
        assert all(-.003 <= gap <= .0015 for gap in geometry["contact_surface_gaps_m"].values())
    assert required <= set(geometry["phases_checked"]), "USD geometry was not audited through every manipulation phase"
    assert set(geometry["fragments"]) == {fragment["id"] for fragment in fragments}
    assert all(record["fragment_count"] == 6 for record in geometry["records"])
    assert recording["geometry_validation"]["passed"] is True
    movie = directory / "pelagic-pip.mp4"
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height,nb_read_frames,r_frame_rate",
                            "-show_entries", "format=duration,size", "-of", "json", str(movie)],
                           capture_output=True, text=True, check=True)
    data = json.loads(probe.stdout)
    stream = data["streams"][0]
    assert [stream["width"], stream["height"]] == recording["composite_resolution"]
    assert int(stream["nb_read_frames"]) == schedule["frame_count"] == recording["frames"]
    assert float(Fraction(stream["r_frame_rate"])) == recording["fps"]
    assert abs(float(data["format"]["duration"]) - schedule["duration_seconds"]) < .1
    assert int(data["format"]["size"]) > 100000
    return {"result": "PASS", "movie": str(movie), "video": data,
            "camera_paths": recording["camera_paths"], "metrics": metrics, "server_started": False,
            "fragment_ids": [f["id"] for f in placed], "action_states_witnessed": sorted(witnessed),
            "detection_validation": detection,
            "geometry_validation": {key: value for key, value in geometry.items() if key not in ("records", "fragments")}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.directory), indent=2))
