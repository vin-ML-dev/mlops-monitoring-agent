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
