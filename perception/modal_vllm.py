"""Serve Gemma on Modal with vLLM's OpenAI-compatible server, for perception/.

NOT run by tests or CI. Spends Modal GPU credits: check with the teammate who
owns the Modal account before deploying (CLAUDE.md section 3).

One-time setup (by the Modal account owner):
    pip install modal && modal setup
    modal secret create huggingface HF_TOKEN=<token with Gemma licence accepted>
    modal secret create gemma-endpoint GEMMA_API_KEY=<any long random string>

Deploy / tear down:
    modal deploy perception/modal_vllm.py      # prints the https://...modal.run URL
    modal app stop reef-gemma

Then in .env:
    GEMMA_BASE_URL=https://<workspace>--reef-gemma-serve.modal.run/v1
    GEMMA_API_KEY=<same string as the secret>
    GEMMA_MODEL=gemma-4-31b-it

Notes / unverified assumptions (check before relying on them):
- HF repo id `google/gemma-4-31b-it` (override with GEMMA_HF_REPO at deploy time).
- 31B in bf16 is ~62 GB of weights, so one H100-80GB; the first cold start downloads
  the weights into a Modal Volume and can take 10+ minutes. Set MIN_CONTAINERS=1
  only during the demo window so it stays warm, then set it back to 0.
- This is a remote endpoint. For the "no phone home" story the same client works
  unchanged against `vllm serve` on the sim GPU box (GEMMA_BASE_URL=http://localhost:8000/v1).
"""

import os
import subprocess

import modal

HF_REPO = os.environ.get("GEMMA_HF_REPO", "google/gemma-4-31b-it")
SERVED_NAME = "gemma-4-31b-it"
GPU = os.environ.get("GEMMA_GPU", "H100")
MIN_CONTAINERS = int(os.environ.get("GEMMA_MIN_CONTAINERS", "0"))
VLLM_PORT = 8000
MINUTES = 60

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

hf_cache = modal.Volume.from_name("reef-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("reef-vllm-cache", create_if_missing=True)

app = modal.App("reef-gemma")


@app.function(
    image=image,
    gpu=GPU,
    timeout=20 * MINUTES,
    scaledown_window=10 * MINUTES,
    min_containers=MIN_CONTAINERS,
    volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
    secrets=[modal.Secret.from_name("huggingface"), modal.Secret.from_name("gemma-endpoint")],
)
@modal.concurrent(max_inputs=16)
@modal.web_server(port=VLLM_PORT, startup_timeout=20 * MINUTES)
def serve():
    cmd = [
        "vllm", "serve", HF_REPO,
        "--served-model-name", SERVED_NAME,
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        "--api-key", os.environ["GEMMA_API_KEY"],
        "--max-model-len", "8192",
        "--limit-mm-per-prompt", '{"image": 1}',
    ]
    subprocess.Popen(cmd)
