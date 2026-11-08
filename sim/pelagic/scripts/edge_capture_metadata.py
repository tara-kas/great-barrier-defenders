#!/usr/bin/env python3
"""Capture observed Docker/host metadata without exporting environment values."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="reef-edge-gemma")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = json.loads(run("docker", "inspect", args.container))[0]
    image = json.loads(run("docker", "image", "inspect", record["Image"]))[0]
    host = record["HostConfig"]
    result = {"recordedAtUtc": datetime.now(timezone.utc).isoformat(),
              "hostname": platform.node(), "architecture": platform.machine(),
              "kernel": platform.release(), "containerId": record["Id"],
              "imageId": record["Image"], "startedAt": record["State"]["StartedAt"],
              "imageRepoDigests": image.get("RepoDigests", []),
              "running": record["State"]["Running"], "networkMode": host["NetworkMode"],
              "memoryLimitBytes": host["Memory"], "nanoCpusLimit": host["NanoCpus"],
              "entrypoint": record["Config"]["Entrypoint"], "command": record["Config"]["Cmd"],
              "mounts": [{key: mount.get(key) for key in ("Type", "Source", "Destination", "RW")}
                         for mount in record.get("Mounts", [])],
              "gpu": run("nvidia-smi", "--query-gpu=name,driver_version,power.draw,utilization.gpu", "--format=csv,noheader,nounits"),
              "networkInterfaces": run("docker", "exec", args.container, "cat", "/proc/net/dev"),
              "networkRoutes": run("docker", "exec", args.container, "cat", "/proc/net/route"),
              "containerProcesses": run("docker", "top", args.container, "-eo", "pid,comm,rss")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("running", "networkMode", "imageId", "gpu")}))


if __name__ == "__main__":
    main()
