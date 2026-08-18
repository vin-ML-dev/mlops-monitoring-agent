# Day 4 — model server image: llama.cpp (via llama-cpp-python) serving the GGUF
# on CPU with an OpenAI-compatible API. Downloads the model at startup.
FROM python:3.11-slim

# build tools for compiling llama-cpp-python (slim images don't include them)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*

# llama-cpp-python ships CPU wheels; build tools are a fallback if a wheel is missing.
RUN pip install --no-cache-dir "llama-cpp-python[server]>=0.3" "huggingface_hub>=0.26"

WORKDIR /app
ENV PYTHONPATH=/app

COPY configs/serve.yaml configs/serve.yaml
COPY src/ src/
COPY serving/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
