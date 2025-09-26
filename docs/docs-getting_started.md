# Getting Started

Welcome to pydelling! This guide will help you install and set up pydelling for your numerical modeling workflows.

## Prerequisites

Before installing pydelling, ensure you have:

- **Python 3.10 or higher**
- **uv package manager** (recommended for dependency management)

## Installing uv Package Manager

pydelling uses the modern `uv` package manager for fast and reliable dependency management.

### Linux or macOS
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Windows
Choose one of the following methods:

**PowerShell (recommended):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Or via pip:**
```bash
pip install uv
```
*Note: When using pip, make sure to add the pip scripts folder to your Windows PATH.*

## Installation Methods

### Method 1: Using Project Template (Recommended)

This is the recommended approach for new projects:

1. **Create a new repository** from [project_template_pydelling](https://gitlab.amphos21.com/digital-solutions/project_template_pydelling)

2. **Clone the repository** in VS Code:
   ```bash
   git clone <your-repository-url>
   cd <your-project-directory>
   ```

3. **Create a virtual environment**:
   ```bash
   uv venv
   ```

4. **Activate the virtual environment**:
   - **Windows**: `.venv\Scripts\activate`
   - **Linux/macOS**: `source .venv/bin/activate`

5. **Load pydelling as a submodule**:
   ```bash
   git submodule update --init
   ```

6. **Install dependencies**:
   ```bash
   uv sync
   ```

### Method 2: Direct Installation

For existing projects or standalone usage:

```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

# Install pydelling and dependencies
uv add pydelling
```

## Verification

Verify your installation by running the test suite:

```bash
# Run all tests
python -m pytest pydelling/tests/

# Or run specific test patterns
python -m pytest pydelling/tests/test_*.py
```

If tests pass successfully, pydelling is ready to use!

## Quick Example

Here's a simple example to verify pydelling is working:

```python
import pydelling
from pydelling.readers import VTKReader

# Check version
print(f"pydelling version: {pydelling.__version__}")

# Basic usage example
reader = VTKReader()
print("pydelling is ready to use!")
```

## Development Setup

If you plan to contribute to pydelling:

1. **Fork and clone** the repository
2. **Create a development environment**:
   ```bash
   uv venv --python 3.10
   uv sync --dev
   ```
3. **Install pre-commit hooks** (if available):
   ```bash
   pre-commit install
   ```

## Troubleshooting

### Common Issues

**ImportError for VTK on some systems:**
- VTK installation can be platform-specific
- For Linux ARM64 systems, additional configuration may be needed
- Refer to the platform-specific installation notes in `pyproject.toml`

**Permission Issues on Windows:**
- Run PowerShell as Administrator when installing uv
- Ensure your execution policy allows script execution

**Submodule Issues:**
- If `git submodule update --init` fails, ensure you have access to the pydelling repository
- Check your git credentials and SSH keys

### Getting Help

If you encounter issues:

1. Check the [troubleshooting section](#troubleshooting) above
2. Review the test output for specific error messages
3. Consult the API documentation for usage examples
4. Create an issue in the project repository

## Next Steps

Now that pydelling is installed:

- Explore the [Usage Guide](docs-usage.md) for comprehensive examples
- Check out the [API Reference](readers/api.md) for detailed documentation
- Browse the `code_snippets/` directory for practical examples

Ready to start modeling? Let's dive into the [Usage Guide](docs-usage.md)!
