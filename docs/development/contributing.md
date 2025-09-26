# Development Guide

Welcome to pydelling development! This guide covers everything you need to know to contribute to pydelling, from setting up your development environment to submitting pull requests.

## Table of Contents

- [Development Environment Setup](#development-environment-setup)
- [Contributing Guidelines](#contributing-guidelines)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Release Process](#release-process)

## Development Environment Setup

### Prerequisites

Before setting up the development environment, ensure you have:

- **Python 3.10 or higher**
- **Git** for version control
- **uv package manager** (recommended)
- **VS Code** (recommended IDE)

### Clone and Setup

```bash
# Clone the repository
git clone https://gitlab.amphos21.com/aitirga/pydelling.git
cd pydelling

# Create development environment
uv venv --python 3.11
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

# Install development dependencies
uv sync --dev

# Install pre-commit hooks
pre-commit install

# Verify installation
python -c "import pydelling; print('Development environment ready!')"
```

### Development Dependencies

The development environment includes additional tools:

```toml
[tool.uv.dev-dependencies]
pytest = ">=7.0.0"
pytest-cov = ">=4.0.0"
black = ">=22.0.0"
isort = ">=5.12.0"
flake8 = ">=6.0.0"
mypy = ">=1.0.0"
pre-commit = ">=3.0.0"
sphinx = ">=5.0.0"
mkdocs-material = ">=9.0.0"
```

### IDE Configuration

#### VS Code Setup

Recommended VS Code extensions:
- Python
- Pylance
- GitLens
- Test Explorer

Add to your `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "./.venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.sortImports.args": ["--profile", "black"],
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    }
}
```

## Contributing Guidelines

### Branching Strategy

pydelling uses a Git Flow branching model:

```
main
├── develop
│   ├── feature/new-reader-implementation
│   ├── feature/improve-mesh-preprocessing
│   └── bugfix/fix-vtk-writer-issue
└── hotfix/critical-security-patch
```

### Branch Naming Convention

- **Feature branches**: `feature/[description]`
  - `feature/add-comsol-integration`
  - `feature/improve-dfn-upscaling`

- **Bug fixes**: `bugfix/[description]`
  - `bugfix/fix-memory-leak-in-reader`
  - `bugfix/correct-coordinate-transformation`

- **Refactoring**: `refactor/[description]`
  - `refactor/simplify-mesh-processor`
  - `refactor/optimize-hdf5-writer`

- **Documentation**: `docs/[description]`
  - `docs/update-api-reference`
  - `docs/add-tutorial-examples`

### Creating a Feature Branch

```bash
# Start from develop branch
git checkout develop
git pull origin develop

# Create and checkout feature branch
git checkout -b feature/your-feature-name

# Make your changes...

# Commit with descriptive message
git add .
git commit -m "Add ConnectFlow mesh reader with boundary detection

- Implement ConnectFlowMeshReader class
- Add support for .msh format parsing
- Include boundary condition detection
- Add comprehensive unit tests
- Update documentation with usage examples"

# Push to remote
git push origin feature/your-feature-name

# Create merge request on GitLab
```

### Commit Message Guidelines

Follow conventional commit format:

```
<type>(<scope>): <description>

<body>

<footer>
```

**Types:**
- `feat`: New features
- `fix`: Bug fixes
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or modifying tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(readers): add FEFLOW .dat file reader

Implements comprehensive FEFLOW reader with support for:
- Time series data
- Multiple data types (temperature, pressure, velocity)
- Automatic unit conversion
- Memory-efficient streaming for large files

Closes #123

fix(writers): resolve HDF5 compression issue

Fixed issue where HDF5 files were not properly compressed
when using gzip compression with shuffle filter.

- Enable shuffle filter by default
- Add compression validation
- Update tests to verify compression

Fixes #456
```

## Code Standards

### Python Style Guide

pydelling follows PEP 8 with some modifications:

```python
# Good examples
class MeshPreprocessor:
    """Process and clean mesh data for simulation."""
    
    def __init__(self, mesh_file: str, debug: bool = False):
        self.mesh_file = Path(mesh_file)
        self.debug = debug
        self._mesh_data = None
    
    def remove_duplicate_points(self, tolerance: float = 1e-6) -> int:
        """Remove duplicate points within tolerance.
        
        Args:
            tolerance: Distance tolerance for duplicate detection
            
        Returns:
            Number of points removed
        """
        # Implementation here
        pass
```

### Naming Conventions

- **Files**: snake_case
  - `mesh_preprocessor.py`
  - `vtk_reader.py`

- **Classes**: CamelCase
  - `MeshPreprocessor`
  - `VTKReader`

- **Functions/Methods**: snake_case
  - `remove_duplicates()`
  - `calculate_permeability()`

- **Constants**: UPPER_SNAKE_CASE
  - `DEFAULT_TOLERANCE`
  - `MAX_ITERATIONS`

- **Private members**: leading underscore
  - `_internal_method()`
  - `_cached_data`

### Type Hints

Use type hints for all public APIs:

```python
from typing import Dict, List, Optional, Union, Tuple
from pathlib import Path
import numpy as np

def process_mesh_data(
    mesh_file: Union[str, Path],
    output_format: str = "vtk",
    options: Optional[Dict[str, Any]] = None
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Process mesh data and return coordinates and data fields."""
    pass
```

### Documentation Standards

All public functions and classes must have docstrings:

```python
def calculate_equivalent_permeability(
    fracture_network: np.ndarray,
    domain_size: Tuple[float, float, float],
    method: str = "oda"
) -> np.ndarray:
    """Calculate equivalent permeability tensor for DFN.
    
    This function computes the equivalent permeability tensor for a discrete
    fracture network using various upscaling methods.
    
    Args:
        fracture_network: Array of fracture geometries and properties
        domain_size: Size of the representative volume element (x, y, z)
        method: Upscaling method - 'oda', 'flow_based', or 'tensor'
    
    Returns:
        3x3 permeability tensor in m²
        
    Raises:
        ValueError: If method is not supported
        RuntimeError: If upscaling calculation fails
        
    Example:
        >>> fractures = load_fracture_network("fractures.dat")
        >>> domain = (100.0, 100.0, 50.0)
        >>> k_tensor = calculate_equivalent_permeability(fractures, domain)
        >>> print(f"Kxx = {k_tensor[0, 0]:.2e} m²")
        
    Note:
        The ODA method is fastest but less accurate for highly connected networks.
        Use 'flow_based' for better accuracy at higher computational cost.
    """
    pass
```

## Testing

### Test Structure

Tests are organized by module:

```
pydelling/
├── tests/
│   ├── test_readers/
│   │   ├── test_vtk_reader.py
│   │   ├── test_connectflow_reader.py
│   │   └── test_data/
│   ├── test_writers/
│   ├── test_preprocessing/
│   └── test_utils/
```

### Writing Tests

Use pytest for all tests:

```python
import pytest
import numpy as np
from pathlib import Path
from pydelling.readers import VTKReader
from pydelling.utils import create_test_mesh

class TestVTKReader:
    """Test suite for VTKReader class."""
    
    @pytest.fixture
    def sample_mesh_file(self, tmp_path):
        """Create a sample VTK mesh file for testing."""
        mesh_file = tmp_path / "test_mesh.vtk"
        test_mesh = create_test_mesh(n_points=100, n_cells=50)
        test_mesh.save(mesh_file)
        return mesh_file
    
    def test_read_basic_mesh(self, sample_mesh_file):
        """Test basic mesh reading functionality."""
        reader = VTKReader(sample_mesh_file)
        mesh_data = reader.read()
        
        assert 'points' in mesh_data
        assert 'cells' in mesh_data
        assert len(mesh_data['points']) == 100
        assert 'triangle' in mesh_data['cells']
        
    def test_read_nonexistent_file(self):
        """Test error handling for nonexistent files."""
        with pytest.raises(FileNotFoundError):
            reader = VTKReader("nonexistent.vtk")
            reader.read()
            
    @pytest.mark.parametrize("file_format", ["ascii", "binary"])
    def test_read_different_formats(self, file_format, tmp_path):
        """Test reading different VTK file formats."""
        mesh_file = self.create_test_mesh(tmp_path, format=file_format)
        reader = VTKReader(mesh_file)
        mesh_data = reader.read()
        
        assert mesh_data is not None
        assert len(mesh_data['points']) > 0
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest pydelling/tests/test_readers/test_vtk_reader.py

# Run with coverage
pytest --cov=pydelling --cov-report=html

# Run tests in parallel
pytest -n auto

# Run only integration tests
pytest -m integration

# Run tests with verbose output
pytest -v
```

### Test Data Management

- Keep test data files small (< 1MB)
- Use `pytest.fixture` for test data setup
- Clean up temporary files after tests
- Store large test datasets externally if needed

## Code Quality Tools

### Pre-commit Hooks

The project uses pre-commit hooks to ensure code quality:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 22.10.0
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: ["--profile", "black"]

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        additional_dependencies: [flake8-docstrings]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.0.0
    hooks:
      - id: mypy
```

### Code Formatting

```bash
# Format code with black
black pydelling/

# Sort imports with isort
isort pydelling/

# Run both (automated by pre-commit)
pre-commit run --all-files
```

### Linting

```bash
# Check code with flake8
flake8 pydelling/

# Type checking with mypy
mypy pydelling/
```

## Documentation

### Building Documentation

```bash
# Install documentation dependencies
uv sync --extra docs

# Build documentation locally
mkdocs serve

# Build for production
mkdocs build

# Deploy to GitHub Pages
mkdocs gh-deploy
```

### Writing Documentation

- Use clear, concise language
- Include code examples
- Add type hints to all examples
- Cross-reference related functions
- Update relevant documentation when changing APIs

### API Documentation

API documentation is auto-generated using mkdocstrings:

```markdown
# Module Documentation

## ConnectFlowReader

::: pydelling.readers.ConnectFlowReader
    options:
      show_root_heading: true
      show_source: false
      members_order: source
```

## Performance Considerations

### Profiling

Use built-in profiling tools to identify bottlenecks:

```python
import cProfile
import pstats

def profile_function():
    # Your code here
    pass

# Profile execution
pr = cProfile.Profile()
pr.enable()
profile_function()
pr.disable()

# Analyze results
stats = pstats.Stats(pr)
stats.sort_stats('cumulative')
stats.print_stats(10)
```

### Memory Management

- Use context managers for file operations
- Implement chunked processing for large datasets
- Profile memory usage with `memory_profiler`
- Use generators for large data processing

```python
def process_large_dataset(filename):
    """Process large dataset in chunks."""
    with open(filename, 'r') as f:
        while True:
            chunk = read_chunk(f, chunk_size=1000)
            if not chunk:
                break
            yield process_chunk(chunk)
```

## Release Process

### Version Management

pydelling uses semantic versioning (SemVer):

- **MAJOR.MINOR.PATCH** (e.g., 1.2.3)
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Checklist

1. **Update version number** in `pyproject.toml`
2. **Update CHANGELOG.md** with new features and fixes
3. **Run full test suite** and ensure all tests pass
4. **Build and test documentation**
5. **Create release branch** from develop
6. **Merge to main** via merge request
7. **Tag release** with version number
8. **Create release notes** on GitLab
9. **Deploy documentation** to production

### Creating a Release

```bash
# Update version
git checkout develop
git pull origin develop

# Edit pyproject.toml and CHANGELOG.md
# Commit version updates
git add .
git commit -m "chore: bump version to 1.2.3"

# Create release branch
git checkout -b release/1.2.3

# Final testing and fixes
pytest
mkdocs build

# Merge to main
git checkout main
git merge release/1.2.3

# Tag release
git tag -a v1.2.3 -m "Release version 1.2.3"
git push origin main --tags

# Merge back to develop
git checkout develop
git merge main
```

## Getting Help

### Community Resources

- **GitLab Issues**: Report bugs and request features
- **Internal Documentation**: Check Amphos 21 knowledge base
- **Code Reviews**: Request reviews from team members
- **Team Meetings**: Weekly development sync meetings

### Development Support

For development questions:

1. Check existing issues and documentation
2. Ask in team chat channels
3. Schedule pair programming sessions
4. Request code reviews early and often

---

*Happy coding! Your contributions make pydelling better for everyone.*