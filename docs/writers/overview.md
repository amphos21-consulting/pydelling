# Writers Overview

pydelling provides specialized writers for various output formats commonly used in numerical modeling workflows. These writers handle format-specific requirements while maintaining data integrity and performance.

## Available Writers

### HDF5 Writers

| Writer | Description | Output Format | Use Case |
|--------|-------------|---------------|----------|
| **PflotranHdf5CentroidWriter** | Cell-centered data for PFLOTRAN | `.h5` | Unstructured mesh properties |
| **PflotranHdf5RasterWriter** | Regular grid data for PFLOTRAN | `.h5` | Structured grid simulations |

### Simulation Input Writers

| Writer | Description | Target Software | Key Features |
|--------|-------------|-----------------|--------------|
| **OpenFoamVariableWriter** | OpenFOAM field files | OpenFOAM | Boundary conditions, initial fields |
| **VTKWriter** | Visualization format | ParaView, VisIt | Standard mesh visualization |

### Specialized Writers

| Writer | Description | Output | Applications |
|--------|-------------|---------|--------------|
| **MeshWriter** | Generic mesh output | Various formats | Mesh conversion, export |
| **ParameterWriter** | Simulation parameters | Text, YAML, JSON | Parameter files, configuration |

## Common Usage Patterns

### Basic Writing Workflow

```python
from pydelling.writers import PflotranHdf5CentroidWriter

# Initialize writer
writer = PflotranHdf5CentroidWriter("output.h5")

# Write datasets
writer.write_coordinates(coordinates)
writer.write_dataset('Permeability', permeability_values)
writer.write_dataset('Porosity', porosity_values)

# Finalize
writer.close()
```

### Context Manager Usage

```python
from pydelling.writers import PflotranHdf5RasterWriter

with PflotranHdf5RasterWriter("structured_data.h5") as writer:
    writer.write_grid(dimensions=(100, 50, 20), spacing=(1.0, 1.0, 0.5))
    writer.write_field('Permeability', perm_field)
    writer.write_field('Porosity', poro_field)
# File automatically closed
```

### Batch Writing

```python
from pydelling.writers import VTKWriter

# Write multiple time steps
for time_step, data in enumerate(time_series_data):
    filename = f"results_t{time_step:04d}.vtk"
    writer = VTKWriter(filename)
    writer.write(data)
    writer.close()
```

## Format-Specific Features

### HDF5 Writers

#### Hierarchical Data Organization

```python
from pydelling.writers import PflotranHdf5CentroidWriter

writer = PflotranHdf5CentroidWriter("simulation_input.h5")

# Create groups for different property types
writer.create_group('Material_Properties')
writer.create_group('Boundary_Conditions')

# Write to specific groups
writer.write_to_group('Material_Properties/Permeability', perm_data)
writer.write_to_group('Material_Properties/Porosity', poro_data)
writer.write_to_group('Boundary_Conditions/Pressure', pressure_bc)
```

#### Metadata and Attributes

```python
# Add metadata to datasets
writer.write_dataset('Permeability', perm_data, 
                    attrs={
                        'units': 'm²',
                        'description': 'Intrinsic permeability',
                        'method': 'laboratory_measurements'
                    })

# Add global attributes
writer.add_global_attribute('creation_date', '2024-01-01')
writer.add_global_attribute('model_version', '1.0.5')
```

### OpenFOAM Writers

#### Field File Generation

```python
from pydelling.writers import OpenFoamVariableWriter

# Write velocity field
writer = OpenFoamVariableWriter("0/U")
writer.write_vector_field(
    velocity_data,
    boundary_conditions={
        'inlet': ('fixedValue', [1.0, 0.0, 0.0]),
        'outlet': ('zeroGradient',),
        'walls': ('noSlip',)
    }
)

# Write pressure field
p_writer = OpenFoamVariableWriter("0/p")
p_writer.write_scalar_field(
    pressure_data,
    boundary_conditions={
        'inlet': ('zeroGradient',),
        'outlet': ('fixedValue', 0.0),
        'walls': ('zeroGradient',)
    }
)
```

#### Case Structure Management

```python
from pydelling.writers import OpenFoamCaseWriter

case_writer = OpenFoamCaseWriter("openfoam_case/")

# Write system files
case_writer.write_control_dict(
    start_time=0,
    end_time=1000,
    delta_t=0.1,
    write_interval=100
)

case_writer.write_fv_schemes(
    time_scheme='Euler',
    grad_schemes='Gauss linear',
    div_schemes='Gauss upwind'
)

# Write constant properties
case_writer.write_transport_properties(
    nu=1e-6,  # kinematic viscosity
    rho=1000  # density
)
```

## Advanced Features

### Compression and Optimization

```python
from pydelling.writers import PflotranHdf5CentroidWriter

# Enable compression
writer = PflotranHdf5CentroidWriter(
    "compressed_output.h5",
    compression='gzip',
    compression_level=9,
    shuffle=True  # Improve compression ratio
)

# Write large datasets efficiently
writer.write_dataset_chunked(
    'LargeDataset', 
    large_array,
    chunk_size=(1000, 1000)
)
```

### Parallel Writing

```python
from pydelling.writers import ParallelHDF5Writer
from mpi4py import MPI

comm = MPI.COMM_WORLD
rank = comm.Get_rank()

# Parallel HDF5 writing
writer = ParallelHDF5Writer("parallel_output.h5", comm=comm)

# Each process writes its portion
local_data = generate_local_data(rank)
writer.write_parallel_dataset('data', local_data, global_shape)
```

### Data Validation

```python
from pydelling.writers import VTKWriter
from pydelling.utils import validate_mesh_data

# Validate before writing
if validate_mesh_data(mesh_data):
    writer = VTKWriter("validated_output.vtk")
    writer.write(mesh_data)
else:
    print("Data validation failed")
```

## Integration Examples

### Preprocessing to Simulation Input

```python
from pydelling.readers import VTKReader
from pydelling.preprocessing import MeshPreprocessor
from pydelling.writers import PflotranHdf5CentroidWriter

# Read and process mesh
reader = VTKReader("raw_mesh.vtk")
mesh = reader.read()

processor = MeshPreprocessor(mesh)
processed_mesh = processor.clean_and_repair()

# Calculate properties
permeability = processor.calculate_permeability()
porosity = processor.calculate_porosity()

# Write simulation input
writer = PflotranHdf5CentroidWriter("simulation_input.h5")
writer.write_coordinates(processed_mesh.get_centroids())
writer.write_dataset('Permeability', permeability)
writer.write_dataset('Porosity', porosity)
writer.close()
```

### Multi-format Output

```python
from pydelling.writers import VTKWriter, PflotranHdf5CentroidWriter
from pydelling.postprocessing import ResultsProcessor

# Process results
processor = ResultsProcessor("simulation_results/")
processed_data = processor.extract_final_state()

# Write for visualization
vtk_writer = VTKWriter("results_visualization.vtk")
vtk_writer.write(processed_data)

# Write for further analysis
hdf5_writer = PflotranHdf5CentroidWriter("analysis_data.h5")
hdf5_writer.write_dataset('FinalConcentration', processed_data['concentration'])
hdf5_writer.write_dataset('VelocityField', processed_data['velocity'])
hdf5_writer.close()
```

### Parameter Study Output

```python
from pydelling.writers import ParameterStudyWriter
from pydelling.managers import PflotranManager

# Run parameter study
manager = PflotranManager("template.in")
results = manager.run_parameter_study(parameter_sets)

# Write results summary
writer = ParameterStudyWriter("parameter_study_results/")
writer.write_summary(results)
writer.write_individual_results(results)
writer.create_analysis_report()
```

## Performance Considerations

### Memory Efficiency

```python
# Stream large datasets
def write_large_dataset_streaming(writer, data_generator):
    for chunk in data_generator:
        writer.write_chunk(chunk)
        # Chunk automatically freed from memory
```

### I/O Optimization

```python
# Batch operations
writer = PflotranHdf5CentroidWriter("batch_output.h5")

with writer.batch_mode():
    writer.write_dataset('Dataset1', data1)
    writer.write_dataset('Dataset2', data2)
    writer.write_dataset('Dataset3', data3)
# All writes committed together
```

### Format Selection

| Format | Best For | Advantages | Disadvantages |
|--------|----------|------------|---------------|
| **HDF5** | Large datasets, metadata | Compression, hierarchical | Complex structure |
| **VTK** | Visualization | Standard format | Limited metadata |
| **Text** | Simple data, debugging | Human readable | Large file size |
| **Binary** | Performance critical | Fast I/O | Platform dependent |

## Error Handling and Validation

### Robust Writing

```python
from pydelling.writers import PflotranHdf5CentroidWriter
from pydelling.utils import PydellingError

try:
    with PflotranHdf5CentroidWriter("output.h5") as writer:
        writer.write_dataset('Data', data_array)
        
except PydellingError as e:
    print(f"Writing failed: {e}")
    # Cleanup partial files if necessary
    
except IOError as e:
    print(f"I/O error: {e}")
    # Handle disk space, permissions, etc.
```

### Data Integrity Checks

```python
# Write with verification
writer = PflotranHdf5CentroidWriter("verified_output.h5")
writer.write_dataset('Data', data_array)

# Verify written data
verification_reader = HDF5Reader("verified_output.h5")
read_data = verification_reader.read_dataset('Data')

if np.allclose(data_array, read_data):
    print("Data written successfully")
else:
    print("Data integrity check failed")
```

## Best Practices

### File Organization

```python
# Organize output by simulation type
base_dir = "simulation_outputs/"
timestep_dir = f"{base_dir}/timestep_{t:04d}/"
os.makedirs(timestep_dir, exist_ok=True)

# Write with consistent naming
vtk_file = f"{timestep_dir}/results_{t:04d}.vtk"
hdf5_file = f"{timestep_dir}/data_{t:04d}.h5"
```

### Metadata Management

```python
# Include comprehensive metadata
writer.add_metadata({
    'simulation_date': datetime.now().isoformat(),
    'software_version': pydelling.__version__,
    'input_files': input_file_list,
    'parameters': simulation_parameters,
    'units': unit_system
})
```

### Version Control

```python
# Include version information
writer.add_global_attribute('pydelling_version', pydelling.__version__)
writer.add_global_attribute('file_format_version', '2.0')
writer.add_global_attribute('creation_method', 'automated_workflow')
```

## Troubleshooting

### Common Issues

1. **File permission errors**
   - Check write permissions
   - Ensure directory exists
   - Handle concurrent access

2. **Large file handling**
   - Use compression
   - Implement chunking
   - Monitor disk space

3. **Data type mismatches**
   - Verify data types before writing
   - Use explicit type conversion
   - Check format requirements

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Detailed logging for writing operations
writer = PflotranHdf5CentroidWriter("debug_output.h5", debug=True)
```

---

*For detailed information about specific writers, see the individual writer pages in this section.*