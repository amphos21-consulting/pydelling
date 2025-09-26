# Installation Guide

This page provides detailed installation instructions for pydelling across different platforms and use cases.

## System Requirements

### Minimum Requirements
- **Python**: 3.10 or higher
- **Operating System**: Windows 10+, macOS 10.15+, Ubuntu 18.04+ (or equivalent Linux distribution)
- **Memory**: 4GB RAM (8GB recommended for large mesh processing)
- **Storage**: 1GB free space for installation

### Recommended Requirements
- **Python**: 3.11 or 3.12 (for optimal performance)
- **Memory**: 16GB RAM (for large-scale simulations)
- **Storage**: 5GB+ for development work and example datasets

## Package Manager Installation

### uv Package Manager (Recommended)

pydelling uses `uv` for fast, reliable dependency management.

#### Linux/macOS Installation
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### Windows Installation

**Option 1: PowerShell (Recommended)**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Option 2: Via pip**
```bash
pip install uv
# Add pip Scripts folder to PATH
```

**Option 3: Manual Installation**
1. Download the latest release from [uv releases](https://github.com/astral-sh/uv/releases)
2. Extract to a directory in your PATH
3. Verify installation: `uv --version`

### Alternative: Traditional pip/conda

If you prefer traditional package managers:

```bash
# Using pip
pip install -e .

# Using conda/mamba
conda env create -f environment.yaml
conda activate pydelling
```

## pydelling Installation

### Method 1: Project Template (Recommended for New Projects)

1. **Create from template:**
   ```bash
   # Use the Amphos21 project template
   git clone https://gitlab.amphos21.com/digital-solutions/project_template_pydelling.git my-project
   cd my-project
   ```

2. **Set up environment:**
   ```bash
   uv venv
   # Activate environment (platform-specific)
   source .venv/bin/activate      # Linux/macOS
   .venv\Scripts\activate         # Windows
   ```

3. **Initialize pydelling:**
   ```bash
   git submodule update --init
   uv sync
   ```

### Method 2: Direct Installation

For integration into existing projects:

```bash
# Create new environment
uv venv pydelling-env
source pydelling-env/bin/activate

# Install pydelling
uv add pydelling

# Or for development
uv add pydelling[dev]
```

### Method 3: Development Installation

For contributors and developers:

```bash
# Clone the repository
git clone https://gitlab.amphos21.com/aitirga/pydelling.git
cd pydelling

# Create development environment
uv venv
source .venv/bin/activate

# Install in development mode
uv sync --dev

# Install pre-commit hooks
pre-commit install
```

## Platform-Specific Considerations

### Windows Specific

**PowerShell Execution Policy:**
```powershell
# Check current policy
Get-ExecutionPolicy

# Set policy for installation (if needed)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Visual C++ Build Tools:**
Some dependencies may require Microsoft Visual C++ Build Tools:
- Download from [Microsoft Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
- Or install via chocolatey: `choco install visualstudio2022buildtools`

### macOS Specific

**Xcode Command Line Tools:**
```bash
xcode-select --install
```

**Homebrew Dependencies (if needed):**
```bash
brew install cmake pkg-config
```

### Linux Specific

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install build-essential cmake libgl1-mesa-dev libglu1-mesa-dev
```

**CentOS/RHEL/Fedora:**
```bash
sudo yum groupinstall "Development Tools"
sudo yum install cmake mesa-libGL-devel mesa-libGLU-devel
```

## Environment Verification

### Basic Installation Check

```python
import pydelling
print(f"pydelling version: {pydelling.__version__}")

# Check key dependencies
import numpy, matplotlib, vtk
print("Core dependencies loaded successfully")
```

### Comprehensive Test Suite

```bash
# Run all tests
python -m pytest pydelling/tests/ -v

# Run specific module tests
python -m pytest pydelling/tests/test_readers.py
python -m pytest pydelling/tests/test_writers.py

# Run with coverage
python -m pytest pydelling/tests/ --cov=pydelling
```

### Performance Benchmark

```python
# Quick performance test
from pydelling.utils import benchmark_utils
benchmark_utils.run_basic_benchmark()
```

## Docker Installation (Optional)

For containerized deployments:

```bash
# Build Docker image
docker build -t pydelling .

# Run container
docker run -it --rm -v $(pwd):/workspace pydelling

# Use docker-compose for development
docker-compose up -d
```

## Troubleshooting

### Common Installation Issues

**Issue: VTK Import Errors**
```python
# Check VTK installation
import vtk
print(vtk.vtkVersion.GetVTKVersion())
```

**Solution:**
- Ensure you're using compatible Python version (3.10-3.12)
- For ARM64 Linux: VTK may require special handling
- Try: `uv add vtk --force-reinstall`

**Issue: Mesh Processing Errors**
- Install additional system libraries for mesh processing
- Ubuntu: `sudo apt install libspatialindex-dev`
- macOS: `brew install spatialindex`

**Issue: HDF5 Compatibility**
```bash
# Force specific HDF5 version
uv add "h5py==3.11" --force-reinstall
```

**Issue: Permission Denied (Windows)**
- Run terminal as Administrator
- Check Windows execution policy
- Ensure antivirus isn't blocking installation

### Performance Issues

**Large Mesh Processing:**
- Increase available memory
- Use 64-bit Python
- Consider using HPC resources for large-scale work

**Slow Import Times:**
- Some imports (especially VTK) can be slow on first load
- This is normal behavior

### Getting Additional Help

1. **Check System Requirements:** Ensure your system meets minimum requirements
2. **Update Dependencies:** Run `uv sync --upgrade` to update all packages
3. **Clean Installation:** Remove `.venv` directory and reinstall
4. **Platform-Specific Forums:** Check platform-specific community resources
5. **Issue Tracker:** Report bugs on the project's issue tracker

## Advanced Configuration

### Environment Variables

```bash
# Optimize for HPC environments
export OMP_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=1

# VTK-specific settings
export VTK_SILENCE_GET_VOID_POINTER_WARNINGS=1
```

### Custom Installation Paths

```bash
# Custom installation directory
uv venv --path /custom/path/pydelling-env
```

### Development Dependencies

```bash
# Install additional development tools
uv add --dev pytest coverage black isort pre-commit
```

## Next Steps

After successful installation:

1. **Verify Installation:** Run the test suite
2. **Explore Examples:** Check the `code_snippets/` directory
3. **Read Documentation:** Start with the [Getting Started](docs-getting_started.md) guide
4. **Join Community:** Connect with other pydelling users

---

*Installation complete? Head to [Getting Started](docs-getting_started.md) to begin using pydelling!*
