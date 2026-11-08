#!/usr/bin/env bash
# Isolated optional Gemma service; does not modify the host Python or Isaac.
set -euo pipefail

: "${EDGE_IMAGE:?Set EDGE_IMAGE to a compatible, pinned NVIDIA vLLM image}"
: "${EDGE_CACHE:?Set EDGE_CACHE to a dedicated Hugging Face cache directory}"
: "${EDGE_EVIDENCE:?Set EDGE_EVIDENCE to the directory for benchmark evidence}"
EDGE_MODEL=${EDGE_MODEL:-google/gemma-4-E4B-it}
if [[ "$EDGE_MODEL" != google/gemma-4-E4B-it ]]; then
  : "${EDGE_REVISION:?Custom weights require their own explicit EDGE_REVISION}"
  : "${EDGE_SERVED_MODEL:?Custom weights require an explicit matching EDGE_SERVED_MODEL}"
fi
EDGE_REVISION=${EDGE_REVISION:-4ecc2ba63bcac23ba4a767fc87025b1450f84c9c}
EDGE_SERVED_MODEL=${EDGE_SERVED_MODEL:-gemma-4-E4B-it}
EDGE_NAME=${EDGE_NAME:-reef-edge-gemma}
EDGE_PORT=${EDGE_PORT:-8012}
EDGE_NETWORK=${EDGE_NETWORK:-none}
EDGE_MEMORY=${EDGE_MEMORY:-48g}
EDGE_GPU_FRACTION=${EDGE_GPU_FRACTION:-0.30}
EDGE_CPUS=${EDGE_CPUS:-8}
mkdir -p "$EDGE_CACHE" "$EDGE_EVIDENCE"

if [[ ${1:-} == download ]]; then
  docker run --rm --name "${EDGE_NAME}-download" \
    -v "$EDGE_CACHE:/root/.cache/huggingface" -e HF_HUB_DISABLE_TELEMETRY=1 \
    --entrypoint python "$EDGE_IMAGE" -c \
    'from huggingface_hub import snapshot_download; import sys; print(snapshot_download(sys.argv[1], revision=sys.argv[2], allow_patterns=["*.json","*.safetensors","*.model","*.jinja","tokenizer*"]))' \
    "$EDGE_MODEL" "$EDGE_REVISION"
  exit
fi
if [[ ${1:-} != serve ]]; then
  echo 'Usage: edge_serve.sh download|serve' >&2
  exit 2
fi

case "$EDGE_NETWORK" in
  none) network=(--network none); listen=127.0.0.1 ;;
  bridge) network=(--network bridge -p "127.0.0.1:${EDGE_PORT}:${EDGE_PORT}"); listen=0.0.0.0 ;;
  *) echo 'EDGE_NETWORK must be none or bridge' >&2; exit 2 ;;
esac
docker run -d --name "$EDGE_NAME" --gpus all "${network[@]}" \
  --shm-size 2g --memory "$EDGE_MEMORY" --cpus "$EDGE_CPUS" \
  -v "$EDGE_CACHE:/root/.cache/huggingface:ro" \
  -v "$EDGE_EVIDENCE:/evidence" \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e HF_HUB_DISABLE_TELEMETRY=1 \
  --entrypoint vllm "$EDGE_IMAGE" serve "$EDGE_MODEL" \
  --revision "$EDGE_REVISION" --served-model-name "$EDGE_SERVED_MODEL" \
  --host "$listen" --port "$EDGE_PORT" --max-model-len 4096 \
  --gpu-memory-utilization "$EDGE_GPU_FRACTION" --max-num-seqs 1 \
  --enforce-eager --limit-mm-per-prompt '{"image":1,"audio":0,"video":0}'
