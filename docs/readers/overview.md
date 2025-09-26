# Readers Overview

pydelling provides a comprehensive suite of readers for various file formats and simulation outputs commonly used in numerical modeling. These readers offer a unified interface while maintaining format-specific optimizations.

## Available Readers

### Mesh and Geometry Readers

| Reader | Description | File Types | Key Features |
|--------|-------------|------------|--------------|
| **VTKReader** | VTK format reader | `.vtk`, `.vtu`, `.vtp` | Standard mesh visualization format |
| **FEMReader** | Finite element mesh reader | `.msh`, `.mesh` | GiD and generic FEM meshes |
| **ConnectFlowMeshReader** | ConnectFlow mesh format | `.msh` | Specialized for ConnectFlow simulations |

### Simulation Output Readers

| Reader | Description | Input Format | Output Data |
|--------|-------------|--------------|-------------|
| **ConnectFlowReader** | ConnectFlow simulation results | `.dat`, `.out` | Flow fields, pressure, connectivity |
| **PflotranObservationPointReader** | PFLOTRAN observation data | `-obs-*.dat` | Time series, concentrations, mass balance |
| **OpenFoamReader** | OpenFOAM case reader | Case directories | Velocity, pressure, scalars |

### Data Format Readers

| Reader | Description | File Types | Use Cases |
|--------|-------------|------------|-----------|
| **CentroidReader** | Centroid-based data | `.csv`, `.txt` | Cell-centered properties |
| **RasterFileReader** | Raster/grid data | `.tiff`, `.asc` | DEM, property distributions |
| **StructuredGridReader** | Regular grid data | `.dat`, `.txt` | Structured simulation data |

## Common Usage Patterns

### Basic Reading Workflow

```python
from pydelling.readers import VTKReader

# Initialize reader
reader = VTKReader("simulation_output.vtk")

# Read data
mesh_data = reader.read()

# Access components
points = mesh_data['points']
cells = mesh_data['cells']
point_data = mesh_data['point_data']
cell_data = mesh_data['cell_data']
```

### Data Processing Pipeline

```python
# Multi-format reading
from pydelling.readers import VTKReader, ConnectFlowReader
from pydelling.preprocessing import MeshPreprocessor

# Read mesh
mesh_reader = VTKReader("geometry.vtk")
mesh = mesh_reader.read()

# Read simulation results
sim_reader = ConnectFlowReader("results.dat")
results = sim_reader.read()

# Combine and process
preprocessor = MeshPreprocessor()
combined_data = preprocessor.merge_mesh_and_results(mesh, results)
```

### Error Handling

```python
from pydelling.readers import VTKReader
from pydelling.utils import PydellingError

try:
    reader = VTKReader("data.vtk")
    data = reader.read()
except PydellingError as e:
    print(f"Reading failed: {e}")
    # Handle gracefully
except FileNotFoundError:
    print("File not found")
```

## Reader Configuration

### Memory Management

```python
# For large files
reader = VTKReader("large_file.vtk", 
                   chunk_size=1000,
                   lazy_loading=True)

# Read specific data only
data = reader.read(fields=['pressure', 'velocity'])
```

### Data Filtering

```python
# Spatial filtering
reader.set_bounds(xmin=0, xmax=100, ymin=0, ymax=50)

# Time filtering (for time series data)
reader.set_time_range(start_time=0, end_time=1000)

# Field filtering
reader.set_fields_of_interest(['pressure', 'temperature'])
```

## Format-Specific Notes

### VTK Files
- Supports both ASCII and binary formats
- Automatic detection of file structure
- Efficient memory usage for large datasets

### ConnectFlow Data
- Specialized handling of flow network topology
- Automatic unit conversion
- Integration with mesh connectivity

### PFLOTRAN Output
- Time series data handling
- Multiple species support
- Observation point mapping

### OpenFOAM Cases
- Automatic case structure detection
- Time directory handling
- Field reconstruction

## Best Practices

### Performance Optimization

1. **Use appropriate data types**:
   ```python
   reader = VTKReader("data.vtk", precision='float32')  # vs float64
   ```

2. **Read only needed data**:
   ```python
   data = reader.read(fields=['pressure'], time_range=(100, 200))
   ```

3. **Chunk large files**:
   ```python
   for chunk in reader.read_chunks(chunk_size=1000):
       process_chunk(chunk)
   ```

### Memory Management

```python
# Explicit cleanup
reader = VTKReader("large_file.vtk")
data = reader.read()
del reader  # Free reader memory
```

### Data Validation

```python
# Validate data after reading
from pydelling.utils import validate_mesh_data

reader = VTKReader("mesh.vtk")
data = reader.read()

if validate_mesh_data(data):
    print("Data is valid")
else:
    print("Data validation failed")
```

## Integration Examples

### With Preprocessing

```python
from pydelling.readers import VTKReader
from pydelling.preprocessing import MeshPreprocessor

reader = VTKReader("input.vtk")
mesh = reader.read()

processor = MeshPreprocessor(mesh)
processed_mesh = processor.clean_and_repair()
```

### With Analysis Tools

```python
from pydelling.readers import PflotranObservationPointReader
import matplotlib.pyplot as plt

reader = PflotranObservationPointReader("pflotran-obs-0.dat")
data = reader.read()

# Plot time series
plt.plot(data['time'], data['concentration'])
plt.xlabel('Time [years]')
plt.ylabel('Concentration [mol/L]')
plt.show()
```

### With Writers

```python
from pydelling.readers import ConnectFlowReader
from pydelling.writers import VTKWriter

# Read ConnectFlow data
cf_reader = ConnectFlowReader("connectflow.dat")
data = cf_reader.read()

# Write to VTK for visualization
vtk_writer = VTKWriter("visualization.vtk")
vtk_writer.write(data)
```

## Extending Readers

### Custom Reader Implementation

```python
from pydelling.readers import BaseReader

class CustomFormatReader(BaseReader):
    def __init__(self, filename):
        super().__init__(filename)
    
    def read(self):
        # Implement format-specific reading
        return self._parse_custom_format()
    
    def _parse_custom_format(self):
        # Format-specific parsing logic
        pass
```

### Reader Registration

```python
from pydelling.readers import register_reader

register_reader('custom', CustomFormatReader)

# Now available via factory
reader = get_reader('custom', 'data.custom')
```

## Troubleshooting

### Common Issues

1. **File format detection failures**
   - Specify reader type explicitly
   - Check file headers and extensions

2. **Memory issues with large files**
   - Use chunked reading
   - Implement lazy loading
   - Filter data before loading

3. **Coordinate system problems**
   - Check coordinate conventions
   - Apply necessary transformations
   - Validate spatial bounds

4. **Missing data fields**
   - Verify field names in source files
   - Check for case sensitivity
   - Use field mapping if needed

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

reader = VTKReader("debug_file.vtk")
data = reader.read()  # Will show detailed parsing info
```

---

*For specific reader documentation, see the individual reader pages in this section.*