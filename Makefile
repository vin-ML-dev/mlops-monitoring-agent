# ============================================================================
#  finbot — Day 6: monitoring (Prometheus + Alertmanager + Grafana)
#  Path 1: Prometheus -> Alertmanager -> Slack (no LLM). Run `make help`.
# ============================================================================
.PHONY: help

MON_NS   ?= monitoring
APP_NS   ?= finbot
RELEASE  ?= kps

help:  ## show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---- offline checks ----
.PHONY: test
test:  ## validate manifests, alert rules, dashboard, values (no cluster)
	pytest tests/ -v

# ---- install the monitoring stack ----
.PHONY: repo install slack-secret
repo:  ## add the prometheus-community Helm repo
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update
slack-secret:  ## create the Slack webhook secret (needs SLACK_WEBHOOK in env)
	kubectl create namespace $(MON_NS) --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n $(MON_NS) create secret generic alertmanager-slack \
	  --from-literal=webhook="$$SLACK_WEBHOOK" --dry-run=client -o yaml | kubectl apply -f -
install:  ## install kube-prometheus-stack (trimmed for kind)
	helm install $(RELEASE) prometheus-community/kube-prometheus-stack \
	  -n $(MON_NS) --create-namespace -f monitoring/values-kind.yaml

# ---- wire finbot into monitoring ----
.PHONY: label monitors rules dashboard apply
label:  ## label the gateway Service so the ServiceMonitor can find it
	kubectl -n $(APP_NS) label svc fastapi-gateway-svc app=fastapi-gateway --overwrite
monitors:  ## apply the gateway ServiceMonitor
	kubectl apply -f monitoring/servicemonitor-gateway.yaml
rules:  ## apply the Prometheus alert rules
	kubectl apply -f monitoring/prometheus-rules.yaml
dashboard:  ## apply the Grafana dashboard
	kubectl apply -f monitoring/grafana-dashboard.yaml
apply: label monitors rules dashboard  ## label + monitors + rules + dashboard

# ---- verify ----
.PHONY: status targets
status:  ## show monitoring pods
	kubectl -n $(MON_NS) get pods
targets:  ## open Prometheus to check Status -> Targets (up==1)
	@echo "port-forwarding Prometheus -> http://localhost:9090 (Status > Targets)"
	kubectl -n $(MON_NS) port-forward svc/$(RELEASE)-kube-prometheus-prometheus 9090:9090

# ---- reach the UIs ----
.PHONY: prometheus grafana alertmanager
prometheus:  ## port-forward Prometheus -> localhost:9090
	kubectl -n $(MON_NS) port-forward svc/$(RELEASE)-kube-prometheus-prometheus 9090:9090
grafana:  ## port-forward Grafana -> localhost:3000 (admin/admin)
	kubectl -n $(MON_NS) port-forward svc/$(RELEASE)-grafana 3000:80
alertmanager:  ## port-forward Alertmanager -> localhost:9093
	kubectl -n $(MON_NS) port-forward svc/$(RELEASE)-kube-prometheus-alertmanager 9093:9093

# ---- demo / test alerts ----
.PHONY: test-model-down test-model-up
test-model-down:  ## scale the model to zero (fires ModelDown + breaker)
	kubectl -n $(APP_NS) scale deployment/finbot-model --replicas=0
test-model-up:  ## restore the model (recovery)
	kubectl -n $(APP_NS) scale deployment/finbot-model --replicas=1

# ---- teardown ----
.PHONY: uninstall
uninstall:  ## remove the monitoring stack + finbot monitors/rules
	kubectl delete -f monitoring/grafana-dashboard.yaml -f monitoring/prometheus-rules.yaml \
	  -f monitoring/servicemonitor-gateway.yaml --ignore-not-found
	helm uninstall $(RELEASE) -n $(MON_NS) || true
