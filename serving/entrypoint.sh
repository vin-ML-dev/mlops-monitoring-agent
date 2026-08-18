#!/usr/bin/env bash
# Download the GGUF, then launch the OpenAI-compatible server. If the download
# fails we exit non-zero so Kubernetes restarts the pod (visible failure).
set -euo pipefail

echo "[serve] fetching model..."
python -m src.serving.fetch_model

MODEL_PATH="${LOCAL_DIR:-/models}/${GGUF_FILE:-finbot-qwen3-1.7b-baseline-q8_0.gguf}"
echo "[serve] launching llama.cpp server on :${PORT:-8080} (model: ${MODEL_PATH})"

# --metrics exposes a Prometheus /metrics endpoint on the SAME port (Day 6 scrapes it).
exec python -m llama_cpp.server \
  --model "${MODEL_PATH}" \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --n_ctx "${N_CTX:-2048}" \
  --n_threads "${N_THREADS:-4}" \
  --chat_format "${CHAT_FORMAT:-chatml}"
