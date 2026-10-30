.DEFAULT_GOAL := help
VENV ?= venv
PYTHON ?= python3
UV ?= uv
UV_VERSION := $(shell awk '$$1 == "uv" {print $$2}' .tool-versions)
NODE ?= node
FLY ?= flyctl
ACTIONLINT ?= actionlint
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
CLI := $(VENV)/bin/treestamp

.PHONY: help venv install format format-check lint typecheck test cov ci build distribution-check integration-check hook-check pre-commit-check tui clean web-install web-lint web-typecheck web-test web-cov web-ci web-fake web-serve web-image web-js-test web-browser-test fly-secrets fly-deploy fly-status fly-logs fly-smoke docs-check metadata-check
GITHUB_API_URL ?= http://127.0.0.1:8100
FAKE_PORT ?= 8100
FAKE_FLAGS ?=
FLY_CONFIG ?= web/fly.toml
FLY_PRODUCTION_CONFIG ?= web/fly.toml
FLY_PREVIEW_CONFIG ?= web/fly.preview.toml
FLY_DEPLOY_FLAGS ?=
FLY_HA ?= true
BUILD_COMMIT ?= $(shell git rev-parse HEAD)
SMOKE_REPO ?= reponomics/treestamp
SMOKE_URL ?= https://treestamp.reponomics.org
SMOKE_CHECKOUT ?= .
WEB_VENV := $(abspath $(VENV))
# Extra pytest-cov options for cov and web-cov, e.g. COV_ARGS=--cov-report=xml
COV_ARGS ?=
.PHONY: tls-check fly-production-deploy fly-preview-deploy workflow-check lock-check lock-update web-browser-install uv-check
export UV_PROJECT_ENVIRONMENT := $(abspath $(VENV))
help: ## Show available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "%-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
uv-check: ## Check that uv matches the pinned development tool version
	@test "$$($(UV) --version | awk '{print $$2}')" = "$(UV_VERSION)" || \
	  { echo "Install uv $(UV_VERSION), as pinned in .tool-versions."; exit 1; }
venv: uv-check ## Create the virtual environment
	@test -d "$(VENV)" || $(UV) venv --python $(PYTHON) $(VENV)
lock-check: uv-check ## Reject dependency declarations that differ from the lock
	$(UV) lock --check
lock-update: uv-check ## Resolve intentional dependency upgrades into uv.lock
	$(UV) lock --upgrade
install: uv-check ## Sync locked core, hosted, build, and test dependencies into venv
	$(UV) sync --locked --all-packages --all-extras --no-install-workspace --no-build
	$(UV) sync --locked --all-packages --all-extras --no-build-isolation
format: ## Format Python code
	$(VENV)/bin/ruff format .
format-check: ## Check Python formatting
	$(VENV)/bin/ruff format --check .
lint: ## Lint Python code
	$(VENV)/bin/ruff check .
typecheck: ## Check strict Python types
	$(VENV)/bin/mypy
test: ## Run the regression suite, including headless TUI journeys
	$(PY) -m pytest
cov: ## Run tests with branch coverage
	$(PY) -m pytest --cov --cov-report=term-missing --cov-fail-under=90 $(COV_ARGS)
ci: format-check lint typecheck cov ## Run all local quality gates
docs-check: ## Check retained local documentation links and packaged README URLs
	$(PY) scripts/check_docs.py
metadata-check: ## Check built metadata, README rendering, package contents, and hashes
	$(PY) -m twine check --strict dist/*.whl dist/*.tar.gz
	$(PY) scripts/release_check.py
build: install ## Sync locked build tools and build wheel and sdist without isolation
	$(PY) -m build --no-isolation
distribution-check: ## Verify clean wheel/sdist headless commands and editor workflows
	$(PY) scripts/distribution_check.py
.PHONY: readme-styles-check readme-update
readme-styles-check: ## Verify alternate README styles match its managed tree
	$(PY) scripts/readme_styles.py
readme-update: ## Refresh the managed README tree and all style previews
	$(CLI) update README.md
	$(PY) scripts/readme_styles.py --write
integration-check: ## Verify the README tree and all alternate style previews
	$(CLI) check README.md
	$(PY) scripts/readme_styles.py
workflow-check: ## Validate GitHub Actions workflows (requires actionlint)
	$(ACTIONLINT)
hook-check: ## Exercise installed repository hooks at HEAD
	$(PY) scripts/hook_check.py
pre-commit-check: ## Run the repository development hooks
	$(VENV)/bin/pre-commit run --all-files
tui: ## Open the editor
	$(CLI)
clean: ## Remove generated build and coverage artifacts
	rm -rf dist/ build/ .coverage htmlcov/ coverage.xml web/.coverage web/coverage.xml
web-install: install ## Sync the locked workspace, including hosted development dependencies
web-browser-install: install ## Sync the locked browser test dependencies (install Chromium separately)
web-lint: ## Lint the web editor project
	$(VENV)/bin/ruff check web && $(VENV)/bin/ruff format --check web
web-typecheck: ## Check strict types for the web editor project
	cd web && $(WEB_VENV)/bin/mypy
web-test: ## Run the web editor tests
	cd web && $(WEB_VENV)/bin/python -m pytest
web-cov: ## Run the web editor tests with branch coverage
	cd web && $(WEB_VENV)/bin/python -m pytest --cov --cov-report=term-missing --cov-fail-under=90 $(COV_ARGS)
web-ci: web-lint web-typecheck web-cov web-js-test ## Run all web editor quality gates
web-js-test: ## Run the page's pure-logic tests with Node's test runner
	$(NODE) --test web/tests/js/*.test.mjs
web-browser-test: ## Drive the page in a browser (needs make install and a browser)
	cd web && $(WEB_VENV)/bin/python -m pytest -q -o addopts="" -m browser tests/browser $(BROWSER_FLAGS)
web-fake: ## Serve this checkout as a fake GitHub API on FAKE_PORT (FAKE_FLAGS adds failure modes)
	$(PY) web/scripts/fake_github.py --repo . --port $(FAKE_PORT) $(FAKE_FLAGS)
web-serve: ## Run the web editor locally against GITHUB_API_URL
	GITHUB_API_URL=$(GITHUB_API_URL) GITHUB_RATE_RESERVE=0 $(VENV)/bin/uvicorn --factory treestamp_web.app:create_app --host 127.0.0.1 --port 8000 --reload
tls-check: ## Check Python TLS package versions and certificate trust stores
	$(PY) web/scripts/check_tls.py
web-image: ## Build the web editor container image
	docker build -f web/Dockerfile --build-arg BUILD_COMMIT="$(BUILD_COMMIT)" -t treestamp-web:local .
fly-secrets: ## Set the GitHub App secrets on Fly (GITHUB_APP_CLIENT_ID, GITHUB_APP_INSTALLATION_ID, GITHUB_APP_PRIVATE_KEY_FILE)
	@test -n "$(GITHUB_APP_CLIENT_ID)" -a -n "$(GITHUB_APP_INSTALLATION_ID)" -a -n "$(GITHUB_APP_PRIVATE_KEY_FILE)" || \
	  { echo "usage: make fly-secrets GITHUB_APP_CLIENT_ID=... GITHUB_APP_INSTALLATION_ID=... GITHUB_APP_PRIVATE_KEY_FILE=path.pem"; exit 2; }
	$(FLY) secrets set --config $(FLY_CONFIG) GITHUB_APP_CLIENT_ID="$(GITHUB_APP_CLIENT_ID)" \
	  GITHUB_APP_INSTALLATION_ID="$(GITHUB_APP_INSTALLATION_ID)" GITHUB_APP_PRIVATE_KEY="$$(cat $(GITHUB_APP_PRIVATE_KEY_FILE))"
fly-deploy: ## Build and deploy the app selected by FLY_CONFIG (defaults to production)
	$(FLY) deploy --config $(FLY_CONFIG) --dockerfile web/Dockerfile --build-arg BUILD_COMMIT="$(BUILD_COMMIT)" --ha=$(FLY_HA) $(FLY_DEPLOY_FLAGS)
fly-production-deploy: ## Build and deploy the production editor
	$(MAKE) fly-deploy FLY_CONFIG=$(FLY_PRODUCTION_CONFIG) FLY_HA=true
fly-preview-deploy: ## Build and deploy the separate test editor
	$(MAKE) fly-deploy FLY_CONFIG=$(FLY_PREVIEW_CONFIG) FLY_HA=false
fly-status: ## Show the app's machines and health
	$(FLY) status --config $(FLY_CONFIG)
fly-logs: ## Stream the service's log lines from Fly
	$(FLY) logs --config $(FLY_CONFIG)
fly-smoke: ## Run the smoke script against the deployed app (SMOKE_REPO, SMOKE_CHECKOUT)
	$(PY) web/scripts/smoke.py $(SMOKE_URL) --repo $(SMOKE_REPO) --checkout $(SMOKE_CHECKOUT)
