#!/usr/bin/env bash
# Generate traffic through the gateway to exercise latency/throughput metrics.
# Usage: GATEWAY_API_KEY=... ./scripts/loadtest.sh [requests] [concurrency]
# Requires: a port-forward to the gateway on localhost:8000.
set -euo pipefail
N="${1:-100}"
C="${2:-4}"
URL="http://localhost:8000/v1/generate"
KEY="${GATEWAY_API_KEY:?set GATEWAY_API_KEY}"

echo "[loadtest] $N requests, concurrency $C -> $URL"
seq "$N" | xargs -P "$C" -I{} curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" \
  "$URL" -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Explain compound interest."}],"max_tokens":128,"temperature":0.3}'
echo "[loadtest] done"
