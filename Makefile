# D1 Market Intelligence and Competitor Analysis — developer tasks.
#
# The gate (lint + format + types + tests + eval) runs on the local profile with the
# [dev] extra only (no google-cloud-*), matching CI. Override PROFILE=gcp for the managed
# stack, or PROFILE=onprem for the fail-fast migration target.

PY ?= python3.14
VENV ?= .venv
BIN := $(VENV)/bin
PROFILE ?= local

API_APP := market_intelligence.api.app:app
API_HOST ?= 127.0.0.1  # no-auth local dev binds loopback; override deliberately
API_PORT ?= 8100
UI_DIR := ui
DEMO_PORT ?= 8110
TF_DIR := infra/terraform

export MKT_INTEL_PROFILE := $(PROFILE)

# The demo scripts the gate lints. The renderer and the self-test are in this list because the
# served self-test and the browser walkthrough both read the evidence hooks the renderer emits,
# so they are gate-relevant code, not scratch scripts.
DEMO_SCRIPTS := scripts/render_brief_ui.py scripts/demo_selftest.py

.PHONY: venv install install-demo install-gcp lock lint format typecheck test eval gate \
        ui-install ui-check portability \
        demo demo-server demo-selftest demo-browser smoke-local run-api run-ui \
        tf-validate tf-plan clean

venv:
	$(PY) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip

install: venv ## Install the package + dev tooling (NO GCP SDK — local/onprem profile).
	$(BIN)/python -m pip install -e ".[dev]"

install-demo: venv ## Install the pinned headless-browser extra, then fetch its browser binary.
	$(BIN)/python -m pip install -e ".[dev,demo]"
	$(BIN)/python -m playwright install chromium

install-gcp: ## Install with the managed-stack extra (google-genai, discoveryengine, ...).
	$(BIN)/python -m pip install -e ".[gcp,dev]"

lock: ## Recompile every lockfile from pyproject.toml and restore the tag = commit headers.
	$(BIN)/python scripts/lock.py

lint:
	$(BIN)/ruff check src tests $(DEMO_SCRIPTS)

format:
	$(BIN)/ruff format --check src tests $(DEMO_SCRIPTS)

typecheck:
	$(BIN)/mypy src

test:
	$(BIN)/pytest -m "not integration" -q

eval:
	$(BIN)/python eval/run_eval.py

# The full gate, green before any change lands.
portability:
	PYTHONPATH=src $(BIN)/python scripts/portability_demo.py

plugin: ## Render the Agent Plugins 1.0.0 directory from this repo's own declarations.
	python scripts/render_plugin.py --dest dist/plugin

mcp-serve: ## Serve the governed tool catalog over MCP 2026-07-28 (stdio; needs [gcp]).
	python -m market_intelligence.mcp

gate: lint format typecheck test eval demo-selftest portability plugin

ui-install: ## Install the console's pinned dependencies exactly as CI does.
	npm ci --prefix $(UI_DIR)

ui-check: ## The console's gate. assert-hydratable runs LAST, on what the build just made.
	npm --prefix $(UI_DIR) run lint
	npm --prefix $(UI_DIR) test
	NEXT_TELEMETRY_DISABLED=1 npm --prefix $(UI_DIR) run build
	npm --prefix $(UI_DIR) run assert-hydratable

demo: ## Offline demo: run the brief flow + render the static audit-first HTML (scripts/out).
	MKT_INTEL_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/demo.py
	MKT_INTEL_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/render_brief_ui.py scripts/out

demo-server: ## Live, presenter-controlled offline demo server on :$(DEMO_PORT).
	MKT_INTEL_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/demo_server.py --port $(DEMO_PORT)

demo-selftest:
	MKT_INTEL_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/demo_selftest.py

demo-browser: ## Drive the SERVED presenter demo through a real headless browser ([demo] extra).
	MKT_INTEL_PROFILE=local $(BIN)/pytest tests/browser -q -rs

smoke-local: ## End-to-end offline smoke: build a cited brief under the local profile.
	MKT_INTEL_PROFILE=local $(BIN)/mkt-intel brief "savings and account fees" -m SG -v banking

run-api: ## Run the real FastAPI service on :$(API_PORT) (PROFILE=$(PROFILE)).
	$(BIN)/uvicorn $(API_APP) --host $(API_HOST) --port $(API_PORT)

run-ui: ## Run the thin Next.js console (dev server); set NEXT_PUBLIC_API_BASE to the API.
	cd $(UI_DIR) && npm install && npm run dev

tf-plan: ## Terraform plan for the pinned asia-southeast1 deploy (needs terraform.tfvars).
	cd $(TF_DIR) && terraform init -input=false && terraform plan

tf-validate:
	cd $(TF_DIR) && terraform fmt -check -recursive && terraform init -backend=false -input=false && terraform validate

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
