#!/usr/bin/env python3
"""Serve the current browser/gateway with measured local model services only."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reefsim.lab_server import ArchitectureAdapters, make_server


class EdgeAdapters(ArchitectureAdapters):
    def health(self):
        result = super().health()
        services = {
            "gemma": (self.gemma_url.removesuffix("/v1") + "/health", self.gemma_key),
            "cuopt": (self.cuopt_url.rsplit("/", 1)[0] + "/health", self.cuopt_key),
        }
        for name, (url, key) in services.items():
            try:
                headers = {"Authorization": "Bearer " + key} if key else {}
                with urlopen(Request(url, headers=headers), timeout=1.25) as response:
                    ready = response.status == 200
                    if name == "cuopt":
                        payload = json.load(response)
                        solve = payload.get("nativeWarmup", {})
                        ready = (ready and payload.get("ready") is True and solve.get("source") == "cuopt"
                                 and solve.get("solverStatus") == "SUCCESS" and solve.get("configured") is True)
                if name == "gemma" and ready:
                    with urlopen(Request(self.gemma_url + "/models", headers=headers), timeout=1.25) as response:
                        ready = (response.status == 200 and any(model.get("id") == self.gemma_model
                                 for model in json.load(response).get("data", []) if isinstance(model, dict)))
            except Exception:
                ready = False
            result["components"][name].update(ready=ready, readiness="ready" if ready else "error")
        result["pipelineReady"] = all(result["components"][name]["ready"] for name in services)
        result["runtime"] = {"platform": "local_edge", "perceptionResidency": "local_gpu",
                             "readinessCheck": "loopback model health and native solver warmup"}
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--cuopt-env", type=Path, required=True)
    parser.add_argument("--argon-config", type=Path, help="Optional server-only JSON credentials/config")
    args = parser.parse_args()
    env = dict(os.environ)
    if args.argon_config:
        config = json.loads(args.argon_config.read_text())
        for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ARGON_MODEL"):
            if isinstance(config.get(key), str) and config[key]:
                env[key] = config[key]
    for line in args.cuopt_env.read_text().splitlines():
        if line.startswith("CUOPT_API_KEY="):
            env["CUOPT_API_KEY"] = line.split("=", 1)[1]
    env.setdefault("GEMMA_BASE_URL", "http://127.0.0.1:8012/v1")
    env.setdefault("GEMMA_MODEL", "gemma-4-E4B-it")
    env.setdefault("GEMMA_DEPLOYMENT", "robot")
    env.setdefault("CUOPT_ADAPTER_URL", "http://127.0.0.1:8013/solve")
    env.setdefault("CUOPT_DEPLOYMENT", "robot")
    for name in ("GEMMA_BASE_URL", "CUOPT_ADAPTER_URL"):
        if urlsplit(env[name]).hostname not in ("127.0.0.1", "localhost", "::1"):
            parser.error(f"{name} must address a loopback service for the edge gateway")
    server = make_server("127.0.0.1", args.port, architecture=EdgeAdapters(env=env), root=ROOT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
