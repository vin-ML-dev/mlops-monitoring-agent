# Triggering each Day-6 alert (for the demo)

All commands assume the monitoring stack is installed and Prometheus is scraping the gateway.

## ModelDown (critical)
Scale the model to zero — the gateway's breaker opens and kube-state-metrics reports 0 replicas.
```bash
kubectl -n finbot scale deployment/finbot-model --replicas=0
# expect: ModelDown + ModelDependencyUnhealthy -> Slack (critical)
kubectl -n finbot scale deployment/finbot-model --replicas=1   # recover
```

## GatewayDown (critical)
```bash
kubectl -n finbot scale deployment/fastapi-gateway --replicas=0
# expect: GatewayDown -> Slack
kubectl -n finbot scale deployment/fastapi-gateway --replicas=1
```

## HighBackendErrorRate (warning)
Scale the model to zero and keep sending traffic — every backend call fails.
```bash
kubectl -n finbot scale deployment/finbot-model --replicas=0
GATEWAY_API_KEY=... ./scripts/loadtest.sh 200 4
# expect: HighBackendErrorRate after ~5m
```

## HighLatencyDegraded (warning)
Push heavy concurrent load so p95 climbs past the threshold (CPU model on one node).
```bash
GATEWAY_API_KEY=... ./scripts/loadtest.sh 400 16
# expect: HighLatencyDegraded if p95 > 15s for 5m
```

## PodRestartChurn (warning)
Force repeated restarts (e.g. crashloop via a bad command, or delete the pod several times).
```bash
for i in 1 2 3 4; do kubectl -n finbot delete pod -l app=fastapi-gateway; sleep 20; done
# expect: PodRestartChurn
```

## AgentHeartbeatLost (critical) — Day 7
Dormant now: it only fires once the Day-7 agent emits
`monitoring_agent_heartbeat_timestamp_seconds` and then stops.
