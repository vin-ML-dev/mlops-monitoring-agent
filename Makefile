# ============================================================================
#  finbot — MLOps pipeline  ·  Makefile (Day 1: data  +  Day 2: training/GGUF)
#  Run `make help` to list all targets.
# ============================================================================

.PHONY: help

# ---- variables (override on the command line, e.g. `make tag-data VERSION=data-v1`) ----
HF_USER      ?= vinmlops
MODEL_REPO   ?= $(HF_USER)/finbot-qwen3-1.7b-baseline
GGUF_REPO    ?= $(HF_USER)/finbot-qwen3-1.7b-gguf
MERGED_DIR   ?= outputs/merged/baseline
GGUF_OUT     ?= outputs/gguf/finbot-qwen3-1.7b-baseline-q8_0.gguf
MLRUNS       ?= file:outputs/mlruns
NOTEBOOK     ?= notebooks/day2_finance_qlora.ipynb

help:  ## show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ============================================================================
#  Day 1 — Setup & environment
# ============================================================================
.PHONY: install install-pii hooks

install:  ## install core + dev deps (from pyproject) and pre-commit hooks
	pip install -e ".[dev]"
	pre-commit install

install-pii:  ## add the optional Presidio NER PII layer + spaCy model
	pip install -e ".[pii]"
	python -m spacy download en_core_web_lg

hooks:  ## (re)install the git pre-commit hooks
	pre-commit install

# ============================================================================
#  Day 1 — Data pipeline (ingest -> curate -> build -> validate -> split)
# ============================================================================
.PHONY: data ingest curate build validate split

data:  ## run the full pipeline via DVC (re-runs only what changed)
	dvc repro

ingest:  ## step 1: stream finance-alpaca from Hugging Face
	python -m src.data.ingest

curate:  ## step 2: quality filters + PII scrub
	python -m src.data.curate

build:  ## step 3: chat format + honesty examples
	python -m src.data.build_dataset

validate:  ## step 4: schema + PII-leak check (fails on any leak)
	python -m src.data.validate

split:  ## step 5: random 80/10/10 train/test/val split
	python -m src.data.split

# ============================================================================
#  Day 1 — Quality, versioning, cleanup
# ============================================================================
.PHONY: test lint format tag-data clean

test:  ## run unit tests
	pytest tests/ -v

lint:  ## lint + auto-fix + format
	ruff check --fix .
	ruff format .

format: lint  ## alias for lint (fix + format)

tag-data:  ## tag the current data version (usage: make tag-data VERSION=data-v1)
	git tag -a $(VERSION) -m "data snapshot $(VERSION)"
	@echo "created tag $(VERSION) — push it with: git push origin $(VERSION)"

clean:  ## remove interim/processed data + caches (keeps raw + code)
	rm -rf data/interim/* data/processed/* .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ============================================================================
#  Day 2 — Fine-tuning (GPU)
#  Primary path is the notebook; the module targets are the scripted equivalent.
# ============================================================================
.PHONY: train-setup notebook train merge infer mlflow-ui tag-model

train-setup:  ## install the QLoRA training stack (needs a CUDA GPU)
	pip install -U "transformers>=4.51" "peft>=0.13" "trl>=0.12" "bitsandbytes>=0.46.1" \
	    "accelerate>=1.1" "datasets>=3.1" "mlflow-skinny>=2.17" "huggingface_hub>=0.26" \
	    "sentencepiece>=0.2"

notebook:  ## open the Day 2 fine-tuning notebook (interactive, recommended)
	jupyter notebook $(NOTEBOOK)

train:  ## scripted QLoRA fine-tune (checkpoint-safe, resumes automatically)
	MLFLOW_ALLOW_FILE_STORE=true MLFLOW_TRACKING_URI=$(MLRUNS) python -m src.training.train

merge:  ## merge the LoRA adapter into a full fp16/bf16 model
	python -m src.training.merge

infer:  ## quick sanity generation from the merged model (eyeball only)
	python -m src.training.infer

mlflow-ui:  ## open the MLflow UI on the local run store
	MLFLOW_ALLOW_FILE_STORE=true mlflow ui --backend-store-uri $(MLRUNS) --port 5000

tag-model:  ## tag a model version (usage: make tag-model VERSION=model-v1)
	git tag -a $(VERSION) -m "model release $(VERSION)"
	@echo "created tag $(VERSION) — push it with: git push origin $(VERSION)"

# ============================================================================
#  Day 2 — Push to Hugging Face
# ============================================================================
.PHONY: hf-login push-model

hf-login:  ## log in to the Hugging Face Hub (needs a WRITE token)
	huggingface-cli login

push-model:  ## push the merged model + model card to the Hub
	python -m src.training.push_to_hub

# ============================================================================
#  Day 2 — GGUF export for CPU serving (Day 4 loads this)
#  Tip: do this in a SEPARATE venv so llama.cpp's deps can't break training.
# ============================================================================
.PHONY: gguf-setup gguf-download gguf push-gguf gguf-smoke

gguf-setup:  ## clone llama.cpp + install convert-script deps (ideally in a fresh venv)
	git clone --depth 1 https://github.com/ggml-org/llama.cpp || true
	pip install -r llama.cpp/requirements.txt

gguf-download:  ## download the merged model from the Hub for conversion
	huggingface-cli download $(MODEL_REPO) --local-dir $(MERGED_DIR)

gguf:  ## convert the merged model -> q8_0 GGUF (no build needed)
	mkdir -p $(dir $(GGUF_OUT))
	python llama.cpp/convert_hf_to_gguf.py $(MERGED_DIR) --outfile $(GGUF_OUT) --outtype q8_0
	@echo ">> wrote $(GGUF_OUT)"

push-gguf:  ## upload the GGUF (+ card) to its Hub repo
	huggingface-cli upload $(GGUF_REPO) $(dir $(GGUF_OUT)) . --repo-type model

gguf-smoke:  ## load the GGUF and generate one answer (proves it serves on CPU)
	pip install -q llama-cpp-python
	python -c "from llama_cpp import Llama; \
	m=Llama(model_path='$(GGUF_OUT)', n_ctx=2048, verbose=False); \
	print(m.create_chat_completion(messages=[{'role':'user','content':'What is an ETF?'}], \
	max_tokens=120, temperature=0.3, repeat_penalty=1.2)['choices'][0]['message']['content'])"
