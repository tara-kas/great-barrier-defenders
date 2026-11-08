# Spark edge deployment

On 8 November 2026, Gemma E4B produced five valid structured image responses on
the project's DGX Spark, using its NVIDIA GB10 GPU. The measurement ran inside a
container with **Docker network mode `none`**, only a loopback interface and no
network routes. Weights were downloaded beforehand. This measurement covers local model residency and disconnected image inference.

The hosted deployment uses Modal. The Spark deployment serves Gemma and native cuOpt locally to the browser mission gateway.

## Exact measured runtime

| Item | Observed value |
| --- | --- |
| Machine | `spark-501b`, aarch64, NVIDIA GB10 |
| Driver | `580.178.04` |
| Weights | `google/gemma-4-E4B-it` |
| Weight revision | `4ecc2ba63bcac23ba4a767fc87025b1450f84c9c` |
| Immutable image | `nvcr.io/nvidia/vllm@sha256:9204569b17ee4c0eff75194b8e6e458479c8aee18953b5ab9cf359fcdac659e2` |
| vLLM package | `0.21.0+2325b6f0.nvinternal.26.5.post1.53039255` |
| Transformers | `5.6.0` |
| PyTorch package | `2.12.0a0+5aff3928d8.nv26.5.50603568` |
| Precision / concurrency | BF16, one request sequence, 4,096-token maximum context |
| CUDA graphs / compile | Eager mode; neither CUDA graphs nor torch.compile |

See the [observed container metadata](evidence/edge_runtime_metadata.json),
[raw benchmark and resource samples](evidence/edge_gemma_benchmark.json),
[vLLM startup/request log](evidence/edge_gemma_server.txt), and the exact
[Isaac camera input](evidence/edge_input_isaac.png). The benchmark records the
input SHA-256 and raw provider responses. No response is a fixture.
Package versions above are the measured distribution metadata; startup banners
use shorter development-version strings. Docker reports the listed immutable
reference in [captured `RepoDigests`](evidence/edge_image_repo_digests.json); a fresh registry pull was not needed or performed.

## Measured resource budget

Five requests reused one recorded Isaac-rendered camera image. Prefix and image
caches were enabled; these measurements are not five independent scene trials.
The first request includes first-use kernel compilation. Later requests are
warm repeats. Response validity establishes the interface, not calibrated
perception accuracy: the model reported an unknown gripper state, which cannot
authorize pickup.

| Measurement | Observed value / scope |
| --- | --- |
| Request latencies | 7.793, 5.106, 5.150, 5.052, 5.172 seconds |
| Median / range | 5.150 seconds / 5.052–7.793 seconds |
| Successful structured responses | 5 of 5 |
| GPU model allocation | 14.6 GiB reported by vLLM during loading |
| KV-cache allocation budget | 19.7 GiB reported available to the cache; a capacity allocation, not the minimum required for this workload |
| Container CPU-memory observation | Peak sampled `memory.current`: 6.449 GiB; lifetime cgroup `memory.peak`: 18.397 GiB, including startup; neither is total unified CPU+GPU memory |
| Shared host memory | Minimum available during samples: 69.062 GiB |
| GPU power samples | 14.94–31.92 W; sample mean 28.735 W |
| Resource samples | 127, no sampling errors |

The configured limits were 48 GiB container memory, eight CPU cores and vLLM
GPU-memory utilization 0.30. Limits are not measurements. On GB10,
`nvidia-smi` returned `N/A` for GPU memory, so GPU memory reporting uses the separate vLLM allocation counters. vLLM allocation reports, cgroup values and shared host availability
have different accounting scopes and must not be added together.

The existing Isaac process remained running and the separate cuOpt setup was
active on the same host. The power readings cover the **shared GPU**, not the
isolated inference process, whole-machine wall power, battery endurance or a
complete underwater vehicle. They cannot be used as an exclusive Gemma energy
budget. No hardware power cap was changed.

## Reproduce local inference

Use a compatible NVIDIA Linux machine with Docker GPU support and enough free
memory. The exact image/reference above was already available on Spark. The
[upstream vLLM Gemma recipe](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html)
and [official weights](https://huggingface.co/google/gemma-4-E4B-it) document the
model/runtime family.

From the repository root, configure dedicated writable directories:

```bash
export EDGE_IMAGE=nvcr.io/nvidia/vllm@sha256:9204569b17ee4c0eff75194b8e6e458479c8aee18953b5ab9cf359fcdac659e2
export EDGE_CACHE=/absolute/path/edge-cache
export EDGE_EVIDENCE=/absolute/path/edge-evidence
export EDGE_NAME=reef-edge-gemma
export EDGE_NETWORK=none
bash sim/pelagic/scripts/edge_serve.sh download
bash sim/pelagic/scripts/edge_serve.sh serve
```

The script pins the weight revision, sets offline Hugging Face mode and defaults
to no container network. `EDGE_MEMORY`, `EDGE_CPUS`, `EDGE_GPU_FRACTION`,
`EDGE_PORT`, `EDGE_MODEL`, `EDGE_SERVED_MODEL` and `EDGE_REVISION` are explicit configuration values.
Custom weights require an explicit revision and served name; pass the same name
to the benchmark's `--model` argument and gateway's `GEMMA_MODEL` setting.
The model and revision must be compatible; changing either creates a new result
that needs its own evidence. An existing container name fails rather than
silently replacing another service.

Wait for an actual health response inside the container:

```bash
docker exec "$EDGE_NAME" python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8012/health").status)'
python3 sim/pelagic/scripts/edge_capture_metadata.py --container "$EDGE_NAME" --output "$EDGE_EVIDENCE/edge_runtime_metadata.json"
cp docs/evidence/edge_input_isaac.png "$EDGE_EVIDENCE/edge_input_isaac.png"
docker cp sim/pelagic/scripts/edge_benchmark.py "$EDGE_NAME:/tmp/edge_benchmark.py"
docker exec "$EDGE_NAME" python /tmp/edge_benchmark.py --image /evidence/edge_input_isaac.png --metadata /evidence/edge_runtime_metadata.json --output /evidence/edge_gemma_benchmark.json --repeats 5
```

Save the server log with `docker logs "$EDGE_NAME"` alongside the measurements.
The host directories contain evidence, never service credentials.

For a browser gateway on the same host, stop the dedicated benchmark container,
retain its evidence, and launch with `EDGE_NETWORK=bridge` under an available
container name. This publishes only `127.0.0.1:8012`; the gateway can use
`GEMMA_BASE_URL=http://127.0.0.1:8012/v1`,
`GEMMA_MODEL=gemma-4-E4B-it` and `GEMMA_DEPLOYMENT=robot` when that label accurately
describes the machine's role. Remote access should use an authenticated SSH
tunnel, not a public unauthenticated model port. Bridge mode connects the host gateway to the local model service.

## Native local solver and private browser gateway

The same Spark subsequently ran the real cuOpt 26.10.0 adapter. Its startup
warmup solved two supplied corridors: `direct` cost 1.66666663 and `clearance`
cost 4.02368927, choosing `direct`, with `solverStatus: SUCCESS` in 1,750 ms.
See [raw native warmup](evidence/edge_cuopt_warmup.json),
[observed packages](evidence/edge_cuopt_packages.json), and
[native container metadata](evidence/edge_cuopt_runtime.json). These are actual
GPU solver results for an intentionally small readiness input, not a mission
or evidence of calibrated underwater energy costs.

The measured solver used Python 3.12.3 in an isolated `/opt/edge-cuopt` virtual
environment, mounted read-only into the same pinned base image above. Its
container limits were 8 GiB memory and four CPU cores. `pip check` reported no
broken requirements. The virtual environment is separate because installing
CUDA 12 dependencies into the base image's CUDA 13 Python environment produced
dependency conflicts. The deployment below bakes the same pinned packages into
a new image; that rebuilt image has not itself been benchmarked.

On the GPU host, from the repository root:

```bash
export EDGE_HOME=/absolute/path/edge-runtime
mkdir -p "$EDGE_HOME/evidence"
umask 077
python3 -c 'import secrets; print("CUOPT_API_KEY=" + secrets.token_urlsafe(32))' > "$EDGE_HOME/cuopt.env"
docker build -f sim/pelagic/scripts/edge_cuopt.Dockerfile \
  --build-arg BASE_IMAGE="$EDGE_IMAGE" -t reef-edge-cuopt:26.10.0 \
  sim/pelagic/scripts
docker run -d --name reef-edge-cuopt --gpus all --network host \
  --memory 8g --cpus 4 --env-file "$EDGE_HOME/cuopt.env" \
  -v "$PWD/sim/pelagic/scripts/edge_cuopt_server.py:/edge/edge_cuopt_server.py:ro" \
  -v "$PWD/sim/pelagic/scripts/cuopt_route_adapter.py:/edge/cuopt_route_adapter.py:ro" \
  -v "$EDGE_HOME/evidence:/evidence" reef-edge-cuopt:26.10.0 \
  --port 8013 --warmup-output /evidence/edge_cuopt_warmup.json
python3 sim/pelagic/scripts/edge_gateway.py --port 8091 \
  --cuopt-env "$EDGE_HOME/cuopt.env"
```

Run Gemma in bridge mode as described above. The native solver binds only
`127.0.0.1:8013`, Gemma is published only on `127.0.0.1:8012`, and the browser
gateway binds only `127.0.0.1:8091`. The gateway verifies the loaded Gemma model
ID and the authenticated native solver warmup before reporting ready; it never
turns health readiness into verified mission evidence. The solver's bearer key
stays on the server. The dependency file pins the observed working environment;
it is not a claim of support on arbitrary GPU, Python or CUDA versions.

From a workstation with authenticated Tailscale SSH access, keep this running:

```bash
tailscale ssh smint@spark -N -L 127.0.0.1:18091:127.0.0.1:8091
```

Open `http://127.0.0.1:18091/lab/`. A standard authenticated `ssh -N -L` tunnel
can be used on other hosts. No public model endpoint is required. The measured
loopback deployment is recorded in
[Gemma service metadata](evidence/edge_loopback_gemma_runtime.json) and the
[gateway source hash manifest](evidence/edge_gateway_source.json). The manifest
records the exact copied source snapshot, including uncommitted changes; it
must not be assumed to match subsequent repository edits.
The initial [entrypoint and solver source snapshot](evidence/edge_initial_entrypoints.json)
separately preserves the deployed wrappers and adapter bytes and hashes.
The later [gateway refresh manifest](evidence/edge_gateway_source_v2.json)
includes all 170 runtime, web, configuration, asset and script files; the
already-running native solver still uses the separately preserved initial
entrypoint/adapter. Its [readiness response](evidence/edge_gateway_readiness_v2.json)
records the exact model and native solver checks after that refresh.
The subsequent [v3 source manifest](evidence/edge_gateway_source_v3.json)
preserves actual file modification times and includes the runtime cache fix.
[Live HTTP checks](evidence/edge_gateway_readiness_v3.json) confirmed that HTML,
JavaScript and CSS return `200` with `Cache-Control: no-store` even when given
a future `If-Modified-Since` date. This prevents an old browser module from
being mistaken for the freshly deployed source.

Argon credentials are loaded server-side through `--argon-config`, using a private
mode-0600 JSON file outside Git and web assets. The refreshed gateway uses this
configuration for online assistance. Gemma and cuOpt remain local.

The [current-disturbance episode](evidence/edge-model-current-drop-abort.json)
records local Gemma inspections, native cuOpt planning, fragment collection,
current-induced loss and a safe abort after the assistance timeout. The
[run index](evidence/readiness-run-index.json) binds each episode to its source
manifest and outcome counters.
