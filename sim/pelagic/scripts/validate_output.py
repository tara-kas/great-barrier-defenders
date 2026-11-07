#!/usr/bin/env python3
"""Check evidence from an actual completed Isaac mission, not just import success."""
import argparse
import json
import struct
from pathlib import Path


def validate(directory, expected_sites=4, initial_stock=6):
    state = json.loads((directory / "state.json").read_text())
    metrics, runtime = state["metrics"], state["runtime"]
    assert state["mode"] == "isaac", "Expected actual Isaac runtime"
    assert runtime["isaac_version"].startswith("6.0"), "Expected Isaac Sim 6.0.x"
    assert metrics["mission_complete"], "Mission did not complete"
    assert metrics["verified"] == expected_sites, "Missing verified placements"
    assert metrics["attached"] == expected_sites, "Attachment count mismatch"
    assert metrics["observed"] == metrics["total_corals"], "Incomplete default reef survey"
    assert metrics["inventory"] + metrics["attached"] == initial_stock, "Stock conservation failed"
    assert metrics["duplicate_assignments"] == 0, "Duplicate reservations"
    assert metrics["collisions"] == 0, "Collision guard violation"
    assert runtime["camera_available"] and runtime["overview_available"], "Missing rendered cameras"
    assert runtime["camera_error"] is None, "Camera capture failed"
    for coral in state["corals"]:
        if coral["fragment_attached"]:
            assert coral["health"] == "bleached_alive", "Attachment must not change biological health"
    cameras = {}
    for name in ("overview.png", "rov-camera.png"):
        data = (directory / name).read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n"), f"Invalid PNG: {name}"
        width, height = struct.unpack(">II", data[16:24])
        assert width >= 320 and height >= 200 and len(data) > 4096, f"Empty camera: {name}"
        cameras[name] = [width, height]
    assert (directory / "reef.usda").stat().st_size > 100000, "Missing authored reef scene"
    return {"result": "PASS", "isaac_version": runtime["isaac_version"],
            "metrics": metrics, "camera_dimensions": cameras}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-sites", type=int, default=4)
    parser.add_argument("--initial-stock", type=int, default=6)
    args = parser.parse_args()
    print(json.dumps(validate(args.directory, args.expected_sites, args.initial_stock), indent=2))
