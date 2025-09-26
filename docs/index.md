# Welcome to pydelling Documentation

![pydelling Logo](pydelling_logo.png)

**pydelling** is a comprehensive Python library developed at Amphos 21, designed specifically for mesh preprocessing and numerical modelling workflows. It provides a robust suite of tools for working with various mesh formats, simulation platforms, and data processing tasks.

## What is pydelling?

pydelling serves as a bridge between different numerical modeling tools, offering:

- **Mesh Preprocessing**: Support for GiD, STL files, and other mesh formats
- **Multi-platform Integration**: Seamless compatibility with PFLOTRAN, OpenFOAM, and COMSOL
- **File Format Support**: Comprehensive readers and writers for VTK and HDF5 formats
- **Simulation Management**: Tools for batch execution and parameter studies
- **Postprocessing**: Advanced data analysis and visualization capabilities

## Key Features

### 🔧 **Preprocessing**
- Mesh preprocessing for various formats
- DFN (Discrete Fracture Network) processing and upscaling
- STL file manipulation and closed surface generation

### 📊 **Simulation Management**
- **PflotranManager**: Execute multiple PFLOTRAN runs with parameter variations
- **ComsolManager**: Batch processing and parametric sweeps for COMSOL models
- Support for both local and HPC environments

### 📖 **Readers & Writers**
- Comprehensive file format support (VTK, HDF5, OpenFOAM, etc.)
- Specialized readers for simulation outputs
- Custom data format converters

### 🧮 **Analysis Tools**
- Interpolation and estimation methods
- Geometric utilities
- Postprocessing for multiple simulation platforms

### 🌐 **Web Applications**
- Interactive tools for parameter management
- Streamlit-based interfaces for common workflows

## Quick Start

Get up and running with pydelling in minutes:

```bash
# Create virtual environment with uv
uv venv

# Install pydelling
uv sync

# Run tests to verify installation
python -m pytest pydelling/tests/
```

## Documentation Structure

This documentation is organized into several sections:

- **[Getting Started](docs-getting_started.md)**: Installation and basic setup
- **[User Guide](docs-usage.md)**: Comprehensive usage examples and tutorials
- **API Reference**: Detailed documentation for all modules and classes
- **Examples**: Real-world use cases and code snippets

## Community & Support

pydelling is an active, collaborative project with regular updates and new features. We welcome contributions and feedback from the community.

---

*Ready to get started? Head over to the [Getting Started](docs-getting_started.md) guide!*