# Testing Guide

Comprehensive testing guide for pydelling development.

## Test Structure

```
pydelling/tests/
├── test_readers/
├── test_writers/  
├── test_preprocessing/
├── test_managers/
└── test_utils/
```

## Running Tests

```bash
# All tests
pytest

# Specific module
pytest pydelling/tests/test_readers/

# With coverage
pytest --cov=pydelling --cov-report=html

# Parallel execution
pytest -n auto
```

## Writing Tests

Use pytest conventions:

```python
import pytest
from pydelling.readers import VTKReader

class TestVTKReader:
    def test_basic_functionality(self):
        # Test implementation
        pass
        
    @pytest.fixture
    def sample_data(self):
        # Fixture for test data
        return create_test_mesh()
```

## Test Categories

- **Unit Tests**: Individual function/class testing
- **Integration Tests**: Multi-component workflows  
- **Performance Tests**: Benchmark critical operations
- **Regression Tests**: Prevent breaking changes

For complete testing guidelines, see [Contributing Guide](contributing.md).