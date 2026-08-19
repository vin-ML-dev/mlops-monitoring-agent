# ============================================================================
#  finbot — MLOps pipeline  ·  Makefile  (Day 1 data · Day 2 train · Day 3 gate)
#  Run `make help` to list all targets.
# ============================================================================
.PHONY: help

HF_USER    ?= vinmlops
GGUF_REPO  ?= $(HF_USER)/finbot-qwen3-1.7b-gguf
MLRUNS     ?= file:outputs/mlruns

help:  ## show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---- setup ----
.PHONY: install install-eval
install:  ## install core + dev deps + pre-commit hooks
	pip install -e ".[dev]"
	pre-commit install
install-eval:  ## install the GGUF runtime for the gate (CPU)
	pip install -e ".[eval]"

# ---- Day 1: data (from src/data — see Day 1) ----
.PHONY: data
data:  ## rebuild the dataset pipeline (dvc)
	dvc repro

# ---- Day 2: training (from src/training — see Day 2) ----
.PHONY: train mlflow-ui
train:  ## run the QLoRA fine-tune (GPU)
	MLFLOW_ALLOW_FILE_STORE=true MLFLOW_TRACKING_URI=$(MLRUNS) python -m src.training.train
mlflow-ui:  ## open the MLflow UI on the local run store
	MLFLOW_ALLOW_FILE_STORE=true mlflow ui --backend-store-uri $(MLRUNS) --port 5000

# ---- Day 3: evaluation gate + registry ----
.PHONY: eval gate gate-test register
eval:  ## score the GGUF against the golden set -> eval_report.json
	python -m src.evaluation.evaluate --config configs/eval.yaml

gate:  ## run the gate (pass/fail; exits non-zero to BLOCK a bad model)
	python -m src.evaluation.gate --config configs/eval.yaml

gate-test:  ## prove the gate blocks a bad model (unit tests, no GPU/GGUF)
	pytest tests/test_evaluation.py -v

register:  ## register an approved model (usage: make register VERSION=v1.0.0)
	python -m src.evaluation.register --version $(VERSION)

# ---- Day 4: local Kubernetes cluster (kind) ----
.PHONY: cluster-up cluster-down
cluster-up:  ## create the local kind cluster
	kind create cluster --name $(CLUSTER) --config deploy/kind-cluster.yaml
cluster-down:  ## delete the local kind cluster
	kind delete cluster --name $(CLUSTER)

# ---- Day 4: build + load the model-server image ----
.PHONY: image image-load
image:  ## build the model-server image
	docker build -f serving/Dockerfile -t $(IMAGE) .
image-load:  ## load the image into the kind cluster
	kind load docker-image $(IMAGE) --name $(CLUSTER)

# ---- Day 4: deploy to the cluster ----
.PHONY: secret deploy status logs undeploy
secret:  ## create the HF token secret (needs HF_TOKEN in your env)
	kubectl create namespace $(NS) --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n $(NS) create secret generic hf-token \
	  --from-literal=HF_TOKEN=$$HF_TOKEN --dry-run=client -o yaml | kubectl apply -f -
deploy:  ## apply all manifests (namespace, configmap, deployment, service)
	kubectl apply -f deploy/namespace.yaml
	kubectl apply -f deploy/configmap.yaml
	kubectl apply -f deploy/deployment.yaml
	kubectl apply -f deploy/service.yaml
status:  ## show pods/services in the namespace
	kubectl -n $(NS) get pods,svc -o wide
logs:  ## tail the model server logs
	kubectl -n $(NS) logs -l app=finbot-model -f
undeploy:  ## remove the app from the cluster
	kubectl delete -f deploy/service.yaml -f deploy/deployment.yaml \
	  -f deploy/configmap.yaml --ignore-not-found

# ---- Day 4: reach + smoke-test the server ----
.PHONY: port-forward smoke
port-forward:  ## forward localhost:$(PORT) -> the in-cluster service
	kubectl -n $(NS) port-forward svc/llama-cpp-svc $(PORT):8080
smoke:  ## send one question to the server (run port-forward first)
	SERVER_URL=http://localhost:$(PORT) python -m src.serving.client "What is an ETF versus a mutual fund?"


# ---- Day 5: local dev with docker-compose ----
.PHONY: up down
up:  ## run gateway + redis locally (docker-compose)
	docker compose up --build
down:  ## stop the local stack
	docker compose down

# ---- Day 5: build + load the gateway image ----
.PHONY: gw-image gw-load
gw-image:  ## build the gateway image
	docker build -f gateway/Dockerfile -t $(GW_IMAGE) .
gw-load:  ## load the gateway image into kind
	kind load docker-image $(GW_IMAGE) --name $(CLUSTER)

# ---- Day 5: deploy Node A (redis + gateway) ----
.PHONY: gw-secret gw-deploy gw-status gw-logs gw-undeploy
gw-secret:  ## create the gateway API-key secret (needs GATEWAY_API_KEY in env)
	kubectl -n $(NS) create secret generic gateway-secret \
	  --from-literal=GATEWAY_API_KEY=$$GATEWAY_API_KEY --dry-run=client -o yaml | kubectl apply -f -
gw-deploy:  ## deploy redis + gateway + service + hpa
	kubectl apply -f deploy/redis-deployment.yaml -f deploy/redis-service.yaml
	kubectl apply -f deploy/gateway-configmap.yaml -f deploy/gateway-deployment.yaml
	kubectl apply -f deploy/gateway-service.yaml -f deploy/gateway-hpa.yaml
gw-status:  ## show Node A pods/services
	kubectl -n $(NS) get pods,svc,hpa -l app=fastapi-gateway
gw-logs:  ## tail the gateway logs
	kubectl -n $(NS) logs -l app=fastapi-gateway -f
gw-undeploy:  ## remove redis + gateway
	kubectl delete -f deploy/gateway-hpa.yaml -f deploy/gateway-service.yaml \
	  -f deploy/gateway-deployment.yaml -f deploy/gateway-configmap.yaml \
	  -f deploy/redis-service.yaml -f deploy/redis-deployment.yaml --ignore-not-found

# ---- Day 5: reach + smoke-test ----
.PHONY: gw-forward gw-smoke gw-metrics
gw-forward:  ## forward localhost:8000 -> the gateway service
	kubectl -n $(NS) port-forward svc/fastapi-gateway-svc 8000:8000
gw-smoke:  ## send a request through the gateway (needs GATEWAY_API_KEY)
	curl -s http://localhost:8000/v1/generate -H "Authorization: Bearer $$GATEWAY_API_KEY" \
	  -H 'Content-Type: application/json' \
	  -d '{"messages":[{"role":"user","content":"What is an ETF?"}],"max_tokens":128,"temperature":0}'
gw-metrics:  ## fetch the gateway /metrics
	curl -s http://localhost:8000/metrics | head -40

# ---- quality ----
.PHONY: test lint clean
test:  ## run unit tests
	pytest tests/ -v
lint:  ## lint + auto-fix + format
	ruff check --fix .
	ruff format .
clean:  ## remove eval outputs + caches
	rm -rf outputs/eval/* .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
