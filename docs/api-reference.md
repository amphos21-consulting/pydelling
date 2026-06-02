# API Reference

This section provides comprehensive API documentation for all modules in the pydelling package. All documentation is automatically generated from the Python docstrings in the source code, ensuring it stays up-to-date with the latest code changes.

## Available Modules

- [**Readers**](reference/readers/index.md) - Data readers for various numerical modeling formats
- [**Writers**](reference/writers/index.md) - Data writers for exporting results and meshes  
- [**Preprocessing**](reference/preprocessing/index.md) - Mesh and data preprocessing utilities
- [**Managers**](reference/managers/index.md) - Simulation management and orchestration
- [**Interpolation**](reference/interpolation/index.md) - Data interpolation and estimation methods
- [**Utilities**](reference/utils/index.md) - General utility functions and geometry operations
- [**ParaView Processor**](reference/paraview_processor/index.md) - ParaView integration and visualization filters

## Quick Start

```python
from pydelling.readers import ConnectFlowReader
from pydelling.writers import HDF5RasterWriter
from pydelling.interpolation import SparseDataInterpolator

# Read data
reader = ConnectFlowReader("simulation_results.txt")
data = reader.read()

# Process data
interpolator = SparseDataInterpolator()
interpolated_data = interpolator.interpolate(data)

# Write results
writer = HDF5RasterWriter("output.h5")
writer.write(interpolated_data)
```

## Documentation Features

- **Automatic Generation**: All documentation is extracted directly from Python docstrings
- **Always Current**: Documentation updates automatically with code changes
- **Complete Coverage**: Includes all public classes, methods, and functions
- **Type Annotations**: Shows parameter types and return types where available
- **Usage Examples**: Includes examples from docstrings where provided

Each module page shows all classes and methods with their complete docstring documentation, including parameters, return values, examples, and usage notes.