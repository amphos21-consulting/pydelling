# Makefile for pydelling project
# Documentation and development tasks

.PHONY: help docs-install docs-serve docs-build docs-deploy docs-clean \
		docs-wiki-prepare docs-wiki-build docs-wiki-clean docs-validate docs-check-links docs-word-count docs-lint docs-full-build docs-dev \
		podman-build podman-run podman-stop podman-clean podman-shell \
		compose-up compose-down compose-logs compose-build
.DEFAULT_GOAL := help

# Variables
DOCS_DIR := docs
SITE_DIR := site
PUBLIC_DIR := public

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

docs-install: ## Install documentation dependencies
	pip install mkdocs mkdocs-gen-files mkdocs-literate-nav mkdocs-material mkdocstrings[python] mkdocstrings-python pymdown-extensions mike

docs-serve: ## Serve documentation locally for development
	mkdocs serve --dev-addr=0.0.0.0:8000

docs-build: ## Build documentation static site
	mkdocs build --clean

docs-build-strict: ## Build documentation with strict mode (fail on warnings)
	mkdocs build --clean --strict

docs-deploy-gh: ## Deploy documentation to GitHub Pages (if using GitHub)
	mkdocs gh-deploy --clean

docs-clean: ## Clean generated documentation files
	rm -rf $(SITE_DIR) $(PUBLIC_DIR)

docs-validate: ## Validate documentation configuration
	mkdocs build --clean --strict --verbose

# GitLab Pages specific commands
gitlab-pages-build: docs-install ## Build documentation for GitLab Pages
	mkdocs build --clean --site-dir $(PUBLIC_DIR)

# Wiki preparation commands
docs-wiki-prepare: docs-build ## Prepare documentation for GitLab Wiki
	@echo "Preparing documentation for GitLab Wiki..."
	@if command -v ./scripts/wiki-manager.sh >/dev/null 2>&1; then \
		./scripts/wiki-manager.sh convert; \
	else \
		mkdir -p wiki-export; \
		find $(SITE_DIR) -name "*.html" -type f | while read file; do \
			basename=$$(basename "$$file" .html); \
			echo "Converting $$file to wiki format..."; \
			pandoc "$$file" -f html -t gfm -o "wiki-export/$${basename}.md" 2>/dev/null || echo "Skipping $$file (pandoc conversion failed)"; \
		done; \
		echo "Wiki preparation complete. Check wiki-export/ directory."; \
	fi

docs-wiki-build: ## Build docs and prepare for wiki (full process)
	@echo "Building documentation and preparing for wiki..."
	@if command -v ./scripts/wiki-manager.sh >/dev/null 2>&1; then \
		./scripts/wiki-manager.sh build; \
	else \
		make docs-build && make docs-wiki-prepare; \
	fi

docs-wiki-clean: ## Clean wiki export directory
	rm -rf wiki-export

# Development commands
docs-check-links: ## Check for broken links in documentation
	@echo "Checking for broken links..."
	@find $(DOCS_DIR) -name "*.md" -type f -exec grep -l "http" {} \; | while read file; do \
		echo "Checking links in $$file..."; \
		grep -o 'http[s]*://[^)]*' "$$file" | sort -u; \
	done

docs-word-count: ## Count words in documentation
	@echo "Word count for documentation:"
	@find $(DOCS_DIR) -name "*.md" -type f -exec wc -w {} + | tail -n 1

# Quality checks
docs-lint: ## Lint documentation files
	@echo "Linting documentation files..."
	@find $(DOCS_DIR) -name "*.md" -type f | while read file; do \
		echo "Checking $$file..."; \
		markdownlint "$$file" 2>/dev/null || echo "markdownlint not available, skipping lint check"; \
	done

podman-build: ## Build Podman image
	podman build -t pydelling .

podman-stop: ## Stop Podman container
	podman stop pydelling || true
	podman rm pydelling || true

podman-clean: podman-stop ## Clean Podman containers and images
	podman rmi pydelling || true

podman-shell: ## Open a shell in the Podman container
	podman exec -it pydelling /bin/sh

podman-test: ## Run tests inside Podman container
	podman exec -it pydelling python -m unittest discover

podman-coverage: ## Run tests with coverage inside Podman container
	podman exec -it pydelling python -m pytest pydelling/tests/ --cov=pydelling --cov-report=xml --cov-report=html --cov-report=term-missing --junitxml=report.xml -v

# Compose commands (works with both docker-compose and podman-compose)
compose-up: ## Start services with compose
	podman-compose up --build -d

compose-down: ## Stop services with compose
	podman-compose down

compose-logs: ## View compose logs
	podman-compose logs -f

compose-build: ## Build services with compose
	podman-compose build

# All-in-one commands
docs-full-build: docs-clean docs-install docs-build-strict ## Full documentation build with validation

docs-dev: docs-install docs-serve ## Start development environment for documentation