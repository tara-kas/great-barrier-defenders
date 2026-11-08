#!/usr/bin/env python3
"""Measure real, loopback Gemma image inference and local resource telemetry.

Run inside the serving container. No credentials are read. For disconnected
proof use a container launched with --network none and HF_HUB_OFFLINE=1.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import statistics
import subprocess
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


SCHEMA = {"type": "object", "properties": {
    "targetVisible": {"type": "boolean"},
    "objectKind": {"type": "string", "enum": ["coral_colony", "coral_fragment", "other", "unknown"]},
    "appearance": {"type": "string", "enum": ["pigmented", "pale_or_bleached", "bare_skeleton_or_algae", "unknown"]},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "visualEvidence": {"type": "string"}, "uncertainty": {"type": "string"},
    "fragmentVisible": {"type": "boolean"},
    "gripperState": {"type": "string", "enum": ["empty", "holding", "unknown"]}},
    "required": ["targetVisible", "objectKind", "appearance", "confidence", "visualEvidence", "uncertainty", "fragmentVisible", "gripperState"],
    "additionalProperties": False}
PROMPT = ("Describe visible evidence in this actual rendered underwater robot-camera image. "
          "Inspect the central coral, any detached fragment and gripper. If not clearly visible, report unknown. "
          "Appearance does not establish viability, species or genotype. Do not invent hidden evidence. "
          "Return exactly the requested JSON schema, with brief visualEvidence and uncertainty.")


def sample_resources():
    stamp = time.monotonic()
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        name, value = line.split(":", 1)
        if name in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
            memory[name + "KiB"] = int(value.split()[0])
    cgroup = {}
    for name in ("memory.current", "memory.peak"):
        path = Path("/sys/fs/cgroup") / name
        if path.exists():
            cgroup[name] = int(path.read_text())
    command = ["nvidia-smi", "--query-gpu=name,utilization.gpu,power.draw,memory.used,memory.total",
               "--format=csv,noheader,nounits"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    return {"monotonicSeconds": stamp, "hostMemory": memory, "containerMemoryBytes": cgroup,
            "gpuCsv": result.stdout.strip() if result.returncode == 0 else None}


def post(url, body):
    with urlopen(Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=180) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8012/v1")
    parser.add_argument("--model", default="gemma-4-E4B-it")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    endpoint = urlsplit(args.endpoint)
    if endpoint.hostname not in ("127.0.0.1", "localhost", "::1") or endpoint.scheme != "http" or endpoint.username or endpoint.password:
        parser.error("benchmark endpoint must be unauthenticated loopback HTTP")
    if not 1 <= args.repeats <= 20:
        parser.error("repeats must be 1–20")
    image = args.image.read_bytes()
    mime = "image/png" if image.startswith(b"\x89PNG") else "image/jpeg"
    image_url = f"data:{mime};base64," + base64.b64encode(image).decode()
    body = {"model": args.model, "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": image_url}}, {"type": "text", "text": PROMPT}]}],
        "max_tokens": 256, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False},
        "structured_outputs": {"json": SCHEMA, "whitespace_pattern": ""}}
    report = {"schema": "reef-edge-benchmark/v1", "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
              "deployment": json.loads(args.metadata.read_text()), "machine": platform.machine(),
              "runtimeVersions": {name: importlib.metadata.version(name) for name in ("vllm", "torch", "transformers")},
              "image": {"name": args.image.name, "sha256": hashlib.sha256(image).hexdigest(), "bytes": len(image),
                        "source": "existing Isaac rendered robot camera; image inference only, no actuation"},
              "model": args.model, "endpoint": args.endpoint, "requestSettings": {"prompt": PROMPT, "schema": SCHEMA, "maxTokens": 256},
              "samples": [], "resourceSamples": [], "resourceErrors": []}
    with urlopen(args.endpoint + "/models", timeout=10) as response:
        report["servedModels"] = json.load(response)
    stop = threading.Event()

    def monitor():
        while not stop.is_set():
            try:
                report["resourceSamples"].append(sample_resources())
            except Exception as error:
                report["resourceErrors"].append(type(error).__name__)
            stop.wait(0.2)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    time.sleep(2)
    try:
        for index in range(args.repeats):
            started = time.monotonic()
            result = post(args.endpoint + "/chat/completions", body)
            duration = time.monotonic() - started
            choice = result["choices"][0]
            parsed = json.loads(choice["message"]["content"])
            from jsonschema import validate
            validate(parsed, SCHEMA)
            if choice.get("finish_reason") != "stop":
                raise ValueError("inference did not finish normally")
            report["samples"].append({"index": index, "startedMonotonicSeconds": started,
                                      "latencySeconds": duration, "response": result, "parsed": parsed})
    finally:
        stop.set()
        thread.join(timeout=6)
        latencies = [sample["latencySeconds"] for sample in report["samples"]]
        report["summary"] = {"completed": len(latencies), "requested": args.repeats,
                             "latencyMinSeconds": min(latencies) if latencies else None,
                             "latencyMedianSeconds": statistics.median(latencies) if latencies else None,
                             "latencyMaxSeconds": max(latencies) if latencies else None}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"]))


if __name__ == "__main__":
    main()
