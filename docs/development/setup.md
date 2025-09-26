# Development Setup

Detailed guide for setting up a pydelling development environment.

## Prerequisites

- Python 3.10+
- Git
- uv package manager
- VS Code (recommended)

## Quick Setup

```bash
# Clone repository
git clone https://gitlab.amphos21.com/aitirga/pydelling.git
cd pydelling

# Create development environment
uv venv --python 3.11
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in development mode
uv sync --dev

# Install pre-commit hooks
pre-commit install

# Verify setup
python -c "import pydelling; print('Ready for development!')"
```

## Development Tools

- **Testing**: pytest with coverage
- **Formatting**: black + isort
- **Linting**: flake8 + mypy
- **Documentation**: mkdocs + mkdocstrings

For complete details, see [Contributing Guide](contributing.md).