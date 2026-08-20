# finbot — a finance-education LLM platform (MLOps, end to end)

A small **finance-education assistant** built the production way: curate data →
fine-tune (QLoRA) → gate on quality → serve in-cluster on CPU → resilient gateway →
**deterministic monitoring**. This repo covers **Days 1–6**.

```
Day 1  DATA     ingest → curate (quality + PII) → build → validate → split
Day 2  TRAIN    QLoRA fine-tune → merge → push (model + GGUF) to the Hub
Day 3  GATE     score the GGUF vs a golden set → pass/fail → register a version
Day 4  SERVE    run the GGUF in-cluster on CPU (llama-cpp-svc)
Day 5  GATEWAY  resilient FastAPI gateway + Redis (fastapi-gateway-svc)
Day 6  MONITOR  Prometheus + Alertmanager + Grafana → Slack (Path 1, no LLM)        ← this repo
Day 7+ AGENT    LangGraph explanation layer (Path 2) + dead-man switch (Node C)
```

---

## Day 6 — deterministic monitoring (this repo's focus)

Build the **reliable alerting core** — **Prometheus decides what's wrong, Alertmanager decides who's
notified** — with **no LLM agent**. This is **Path 1** from the architecture: it must fire even if
the Day-7 agent is dead.

```
Gateway /metrics ─┐
(fastapi-gateway) │
                  ├──> Prometheus ──> Alert Rules ──> Alertmanager ──> Slack   (Path 1)
Model health ─────┘     (StatefulSet)                 (StatefulSet)
(via gateway +               └──> Grafana (Deployment · dashboards)
 kube-state-metrics)
```

**What's implemented**

- **kube-prometheus-stack**, trimmed for single-node kind (`monitoring/values-kind.yaml`) — Prometheus
  + Alertmanager (StatefulSets) + Grafana (Deployment) + kube-state-metrics.
- **Gateway ServiceMonitor** — Prometheus scrapes the Day-5 gateway's `/metrics`.
- **Alert rules** (`monitoring/prometheus-rules.yaml`) wired to the **real** gateway metrics:
  `GatewayDown`, `ModelDown`, `ModelDependencyUnhealthy` (breaker open), `HighBackendErrorRate`,
  `HighLatencyDegraded`, `PodRestartChurn`, and `AgentHeartbeatLost` (dormant until Day 7).
- **Alertmanager → Slack** — grouping, severity routing (warning vs critical), `repeat_interval`,
  resolved messages; the webhook comes from a **Kubernetes Secret**.
- **Grafana dashboard** — auto-loaded (request rate, p95, backend error ratio, breaker, cache, restarts).

**Model health without the model's own `/metrics`.** The Day-4 model runs `llama-cpp-python`, which
has **no `/metrics`**. So Day 6 detects the model from the **caller's side** — the gateway's backend
error ratio + circuit-breaker gauge — plus **kube-state-metrics** (replicas available, pod restarts).
Scraping the model directly is an optional file for when you switch to the native server (Day 8).

---

## Run Day 6 (needs Day 4 + Day 5 already deployed)

```bash
# install the stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts && helm repo update
kubectl create ns monitoring
export SLACK_WEBHOOK='https://hooks.slack.com/services/XXX/YYY/ZZZ'
kubectl -n monitoring create secret generic alertmanager-slack --from-literal=webhook="$SLACK_WEBHOOK"
helm install kps prometheus-community/kube-prometheus-stack -n monitoring -f monitoring/values-kind.yaml

# wire finbot into monitoring
kubectl -n finbot label svc fastapi-gateway-svc app=fastapi-gateway --overwrite
kubectl apply -f monitoring/servicemonitor-gateway.yaml
kubectl apply -f monitoring/prometheus-rules.yaml
kubectl apply -f monitoring/grafana-dashboard.yaml

# verify targets (Status -> Targets, expect up==1 for the gateway)
kubectl -n monitoring port-forward svc/kps-kube-prometheus-prometheus 9090:9090

# demo an alert
kubectl -n finbot scale deployment/finbot-model --replicas=0    # -> ModelDown -> Slack
kubectl -n finbot scale deployment/finbot-model --replicas=1    # -> recovery
```

*(Make equivalents: `make repo`, `make slack-secret`, `make install`, `make apply`, `make targets`,
`make test-model-down`. See `make help`.)*

**Offline (no cluster):**
```bash
make test        # validates manifests, alert-rule completeness, dashboard JSON, and the values file
```

---

## Repo layout

```
monitoring/
  values-kind.yaml                    kube-prometheus-stack values (trimmed for kind)
  servicemonitor-gateway.yaml         scrape the gateway /metrics
  servicemonitor-model.OPTIONAL.yaml  scrape the model (only with native server + --metrics)
  prometheus-rules.yaml               the alert rules (Path 1)
  alertmanager-slack-secret.example.yaml
  grafana-dashboard.yaml              auto-loaded dashboard
scripts/
  loadtest.sh                         generate traffic to exercise latency alerts
  trigger_alerts.md                   how to fire each alert for the demo
docs/DAY6_GUIDE.md                    the full theory guide (diagram-matched)
tests/test_monitoring.py              offline validation
Makefile                              install / wire / verify / demo / teardown
```

## Requirements

- **Runtime tools (not pip):** helm, kubectl, kind — plus Day 4 (model) and Day 5 (gateway) running.
- **Python:** only for the offline tests (`pip install -e ".[dev]"`).
- On **single-node kind** everything co-locates; the Node A/B/C split is Day 8.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Gateway target missing in Prometheus | Label the Service: `kubectl -n finbot label svc fastapi-gateway-svc app=fastapi-gateway`. |
| ServiceMonitor ignored | `serviceMonitorSelectorNilUsesHelmValues: false` must be set (it is in `values-kind.yaml`). |
| `GatewayDown` never fires when it should | The `job` label may differ — check Prometheus → Status → Targets and adjust the rule matcher. |
| No Slack messages | Webhook secret missing/wrong, or the channel doesn't exist. Check the Alertmanager pod logs. |
| Stack won't schedule on kind | Reduce resources further in `values-kind.yaml`; give Docker more memory. |
| False `ServiceDown` for the model | Don't apply the model ServiceMonitor unless the model actually serves `/metrics`. |

---

## What each day proves (interview-ready)

- **Days 1–5:** versioned data, gated model, self-healing CPU serving, resilient gateway.
- **Day 6:** **deterministic monitoring first** — Prometheus + PromQL rules detect down/degraded/
  error/restart, Alertmanager groups/routes/repeats and posts to Slack, and it all works with **no
  LLM**. Model health is inferred from caller-side signals when the model has no `/metrics`.

## License

Code: MIT (educational). Base model (`Qwen/Qwen3-1.7B`, Apache-2.0) and dataset carry their own
licenses.

---

**Next — Day 7:** the **LangGraph agent** (Node C) — **Path 2**: it reads the same Prometheus data,
explains *why* an incident is happening in plain English to Slack, and emits a heartbeat that
activates the Day-6 `AgentHeartbeatLost` dead-man switch. The agent **never** remediates.
