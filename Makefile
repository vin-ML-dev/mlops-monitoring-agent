.PHONY: help setup install install-pii data ingest curate build validate split test lint format dvc-repro clean

help:
	@echo "make install      - install dependencies"
	@echo "make install-pii  - add the optional Presidio NER PII layer + spaCy model"
	@echo "make data         - run the full pipeline: ingest -> curate -> build -> validate -> split"
	@echo "make test         - run tests"
	@echo "make lint / format- ruff check / auto-fix"
	@echo "make dvc-repro    - reproduce the DVC pipeline"
	@echo "make clean        - remove generated data + caches"

install:
	pip install -r requirements.txt

install-pii:
	pip install presidio-analyzer presidio-anonymizer spacy
	python -m spacy download en_core_web_lg

data: ingest curate build validate split

ingest:
	python -m src.data.ingest
curate:
	python -m src.data.curate
build:
	python -m src.data.build_dataset
validate:
	python -m src.data.validate
split:
	python -m src.data.split

test:
	pytest -q

lint:
	ruff check .

format:
	ruff format .
	ruff check . --fix

dvc-repro:
	dvc repro

clean:
	rm -rf data/interim/* data/processed/* .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
