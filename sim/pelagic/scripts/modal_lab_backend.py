"""Deploy with: modal deploy scripts/modal_lab_backend.py.

Only the authenticated gateway is public. GPU classes use private Modal RPC.
No inference results, tokens or camera frames are written to disk by this app.
"""
import os
from pathlib import Path
import modal

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "reef-rescue-lab"
HF_REPO = os.environ.get("GEMMA_HF_REPO", "google/gemma-4-E4B-it")
MODEL_NAME = "gemma-4-E4B-it"
app = modal.App(APP_NAME)
cache = modal.Volume.from_name("reef-rescue-gemma-cache", create_if_missing=True)
base = modal.Image.debian_slim(python_version="3.12").pip_install("fastapi==0.135.1")
source = base.add_local_dir(ROOT / "reefsim", "/root/reefsim").add_local_file(ROOT / "scripts/cuopt_route_adapter.py", "/root/cuopt_route_adapter.py")
gemma_image = (modal.Image.from_registry("nvidia/cuda:12.9.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([]).pip_install("vllm==0.21.0").pip_install("transformers==5.10.1")
    .env({"HF_HOME": "/model-cache", "HF_HUB_DISABLE_TELEMETRY": "1"}))
cuopt_image = (modal.Image.from_registry("nvidia/cuda:12.9.0-runtime-ubuntu22.04", add_python="3.12")
    .entrypoint([]).pip_install("cuopt-cu12==26.10.*", extra_index_url="https://pypi.nvidia.com")
    .add_local_file(ROOT / "scripts/cuopt_route_adapter.py", "/root/cuopt_route_adapter.py"))

@app.cls(image=gemma_image, gpu=os.environ.get("REEF_GEMMA_GPU", "L4,A10").split(","),
         secrets=[modal.Secret.from_name("huggingface")], volumes={"/model-cache": cache},
         max_containers=1, cpu=4, memory=16384, scaledown_window=600, timeout=900)
class GemmaRuntime:
    @modal.enter()
    def start(self):
        import json, subprocess, time
        from urllib.request import urlopen
        env = dict(os.environ)
        if not env.get("HF_TOKEN") and env.get("HUGGING_FACE_HUB_TOKEN"):
            env["HF_TOKEN"] = env["HUGGING_FACE_HUB_TOKEN"]
        self.process = subprocess.Popen(["vllm", "serve", HF_REPO, "--host", "127.0.0.1", "--port", "8000",
            "--served-model-name", MODEL_NAME, "--max-model-len", "4096", "--gpu-memory-utilization", "0.88",
            "--max-num-seqs", "1", "--limit-mm-per-prompt", '{"image":1}',
            "--structured-outputs-config", '{"backend":"guidance"}', "--no-enable-log-requests"], env=env)
        deadline = time.monotonic() + 840
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("Gemma model server stopped during initialization")
            try:
                with urlopen("http://127.0.0.1:8000/v1/models", timeout=2) as response:
                    models = json.load(response)
                if any(m.get("id") == MODEL_NAME for m in models.get("data", [])):
                    return
            except Exception:
                pass
            time.sleep(2)
        raise RuntimeError("Gemma readiness deadline exceeded")

    @modal.method()
    def warmup(self):
        return {"ready": True, "model": MODEL_NAME, "deployment": "modal", "check": "loaded_model_server"}

    @modal.method()
    def generate(self, payload):
        import json
        from urllib.request import Request, urlopen
        with urlopen(Request("http://127.0.0.1:8000/v1/chat/completions", json.dumps(payload).encode(),
                             {"Content-Type": "application/json"}), timeout=25) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise RuntimeError("Gemma response exceeded bound")
        return json.loads(raw)

@app.cls(image=cuopt_image, gpu=os.environ.get("REEF_CUOPT_GPU", "T4"),
         max_containers=1, cpu=4, memory=16384, scaledown_window=600, timeout=120)
class CuOptRuntime:
    @modal.method()
    def warmup(self):
        from cuopt_route_adapter import optimize
        result = optimize({"id": "warmup", "alternatives": [{"id": "direct", "points": [[0,0,0],[1,0,0]]}]})
        return {"ready": result["solverStatus"] == "SUCCESS", "model": "nvidia-cuopt", "check": "actual_gpu_solve", "solverVersion": result["solverVersion"]}

    @modal.method()
    def solve(self, payload):
        from cuopt_route_adapter import optimize
        return optimize(payload)

@app.function(image=source, secrets=[modal.Secret.from_name("reef-rescue-runtime")],
              max_containers=1, scaledown_window=600, timeout=60)
@modal.concurrent(max_inputs=16)
@modal.asgi_app()
def gateway():
    import asyncio, hmac, json, threading, time
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from reefsim.lab_server import ArchitectureAdapters, LabError, MAX_BODY
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    gemma, cuopt = GemmaRuntime(), CuOptRuntime()
    def generate(payload):
        try:
            return gemma.generate.remote(payload)
        except Exception:
            raise LabError(502, "Gemma GPU inference failed; no replacement produced") from None
    def solve(payload):
        try:
            return cuopt.solve.remote(payload)
        except Exception:
            raise LabError(502, "cuOpt GPU solve failed; no replacement produced") from None
    env = {**os.environ, "GEMMA_MODEL": MODEL_NAME, "GEMMA_DEPLOYMENT": "modal", "CUOPT_DEPLOYMENT": "modal"}
    adapters = ArchitectureAdapters(env=env, gemma_infer=generate, cuopt_solve=solve)
    runtime = {name: {"state": "not_started", "call": None, "checked": None} for name in ("gemma", "cuopt")}
    lock = threading.Lock()
    def health():
        with lock:
            now = time.monotonic()
            for item in runtime.values():
                if item["state"] == "warming" and item["call"] is not None:
                    try:
                        result = item["call"].get(timeout=0)
                        item["state"] = "ready" if result.get("ready") is True else "error"
                        item["checked"] = now
                    except TimeoutError:
                        pass
                    except Exception:
                        item["state"] = "error"
                elif item["state"] == "ready" and now-item["checked"] > 240:
                    item["state"] = "not_started"
            value = adapters.health()
            for name, item in runtime.items():
                value["components"][name].update(readiness=item["state"], ready=item["state"] == "ready")
            value["components"]["argon"].update(readiness="ready" if adapters.argon.api_key else "unconfigured", ready=bool(adapters.argon.api_key))
            value["pipelineReady"] = all(v["ready"] for v in value["components"].values())
            value["status"] = "ready" if value["pipelineReady"] else "warming" if any(v["state"] == "warming" for v in runtime.values()) else "not_started"
            value["runtime"] = {"platform": "modal", "authentication": "bearer", "perceptionResidency": "remote_gpu", "argonAccessVerified": adapters.status["argon"] == "verified_response"}
            return value
    @api.middleware("http")
    async def authenticate(request: Request, call_next):
        expected = os.environ.get("LAB_GATEWAY_TOKEN", "")
        supplied = request.headers.get("authorization", "")
        if not expected or not hmac.compare_digest(supplied, "Bearer " + expected):
            return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response
    @api.get("/api/lab/architecture")
    @api.get("/api/lab/health")
    async def get_health():
        return await asyncio.to_thread(health)
    @api.post("/api/lab/{operation}")
    async def operate(operation: str, request: Request):
        if operation not in ("warmup", "perception", "plan", "telemetry"):
            return JSONResponse({"ok": False, "error": "Unknown endpoint"}, status_code=404)
        try:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                raise LabError(415, "Expected application/json")
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_BODY:
                    raise LabError(413, "Request too large")
            data = json.loads(body)
            if operation == "warmup":
                if data != {}:
                    raise LabError(400, "Warmup expects an empty object")
                await asyncio.to_thread(health)
                pending = []
                with lock:
                    for name, remote in (("gemma", gemma), ("cuopt", cuopt)):
                        if runtime[name]["state"] in ("not_started", "error"):
                            runtime[name].update(state="warming", call=None, checked=None)
                            pending.append((name, remote))
                for name, remote in pending:
                    try:
                        call = await remote.warmup.spawn.aio()
                        with lock:
                            runtime[name]["call"] = call
                    except Exception:
                        with lock:
                            runtime[name]["state"] = "error"
                result = await asyncio.to_thread(health)
                return JSONResponse(result, status_code=200 if result["pipelineReady"] else 202)
            if operation == "telemetry":
                return adapters.receive_telemetry(data)
            state = await asyncio.to_thread(health)
            needed = ("gemma",) if operation == "perception" else ("gemma", "cuopt")
            if not all(state["components"][name]["ready"] for name in needed):
                raise LabError(503, "GPU services are not ready; request warmup and poll architecture")
            if operation == "plan":
                if not isinstance(data, dict):
                    raise LabError(400, "Planning expects an object")
                data.setdefault("requireFullStack", True)
            result = await asyncio.to_thread(adapters.call, operation, data)
            with lock:
                for name in needed:
                    runtime[name]["checked"] = time.monotonic()
            return result
        except LabError as error:
            return JSONResponse({"ok": False, "error": str(error)}, status_code=error.status)
        except (ValueError, TypeError, RecursionError):
            return JSONResponse({"ok": False, "error": "Invalid request"}, status_code=400)
        except Exception:
            return JSONResponse({"ok": False, "error": "Runtime unavailable; no synthetic replacement used"}, status_code=502)
    return api
