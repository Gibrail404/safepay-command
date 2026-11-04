# One command per job. Every number in README.md and docs/reports/ comes from one of these targets.
PY ?= .venv/bin/python
PG_URL ?= postgresql+psycopg://safepay:safepay_dev_only@127.0.0.1:5433/safepay_test

.PHONY: help data test test-pg models reports-real reports-simulated reports-llm reports console-check load openapi

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ -/'

data:  ## download and verify every real dataset (about 300 MB)
	cd pipelines && ../$(PY) -m safepay_data all

test:  ## unit, invariant and real-data tests on SQLite
	$(PY) -m pytest tests -q

test-pg:  ## the same tests on PostgreSQL, including the concurrency and race tests (needs: docker compose up -d db)
	SAFEPAY_TEST_DATABASE_URL=$(PG_URL) $(PY) -m pytest tests -q

models:  ## train the risk and text models (writes models/ and two reports)
	cd ml && ../$(PY) -m safepay_ml.train_risk && ../$(PY) -m safepay_ml.train_text

reports-real:  ## reports computed on real data: screening, redaction, graph, flywheel
	$(PY) scripts/eval_screening.py && $(PY) scripts/eval_redaction.py && $(PY) scripts/eval_graph.py && $(PY) scripts/eval_flywheel.py

reports-simulated:  ## reports computed on simulated data: Decision Lab, uplift
	$(PY) scripts/eval_lab.py && $(PY) scripts/eval_uplift.py

reports-llm:  ## reports that call a live AI model (need OLLAMA_API_KEY in .env)
	$(PY) scripts/eval_llm.py && $(PY) scripts/eval_sandbox.py && $(PY) scripts/eval_investigator.py

reports: models reports-real reports-simulated reports-llm  ## regenerate every report from raw data

console-check:  ## type check and production build of the console
	cd console && npm ci && npm run typecheck && npm run build

load:  ## local load test against a running API (see docs/reports/load.md)
	$(PY) scripts/load_test.py

openapi:  ## regenerate the API contract
	$(PY) scripts/export_openapi.py
