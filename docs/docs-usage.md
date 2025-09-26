# Usage Guide

This comprehensive guide covers the main features and workflows in pydelling, with practical examples and best practices.

## Table of Contents

- [Core Concepts](#core-concepts)
- [Readers](#readers)
- [Writers](#writers)
- [Preprocessing](#preprocessing)
- [Simulation Management](#simulation-management)
- [Postprocessing](#postprocessing)
- [Web Applications](#web-applications)
- [Advanced Workflows](#advanced-workflows)

## Core Concepts

### Working with Mesh Data

pydelling provides a unified interface for handling various mesh formats:

```python
from pydelling.readers import VTKReader, ConnectFlowReader
from pydelling.writers import VTKWriter

# Read different formats
vtk_reader = VTKReader("data/mesh.vtk")
cf_reader = ConnectFlowReader("data/connectflow_output.dat")

# Process data
mesh_data = vtk_reader.read()
flow_data = cf_reader.read()

# Write results
writer = VTKWriter("output/processed_mesh.vtk")
writer.write(mesh_data)
```

### Data Structure Overview

pydelling uses consistent data structures across modules:

```python
# Standard mesh data structure
mesh = {
    'points': numpy_array,      # Vertex coordinates
    'cells': dict,              # Cell connectivity
    'point_data': dict,         # Data at vertices
    'cell_data': dict,          # Data at cell centers
    'metadata': dict            # Additional information
}
```

## Readers

pydelling provides specialized readers for various simulation outputs and mesh formats.

### VTK Files

```python
from pydelling.readers import VTKReader

# Basic VTK reading
reader = VTKReader("simulation_output.vtk")
mesh = reader.read()

# Access data
points = mesh['points']
pressure = mesh['point_data']['pressure']
temperature = mesh['cell_data']['temperature']

print(f"Mesh contains {len(points)} points")
print(f"Available point data: {list(mesh['point_data'].keys())}")
```

### ConnectFlow Data

```python
from pydelling.readers import ConnectFlowReader

# Read ConnectFlow simulation output
reader = ConnectFlowReader("connectflow_results.dat")
data = reader.read()

# Process flow data
flow_rates = data.get_flow_rates()
pressure_field = data.get_pressure_field()

# Export to VTK for visualization
data.export_vtk("connectflow_visualization.vtk")
```

### PFLOTRAN Results

```python
from pydelling.readers import PflotranObservationPointReader

# Read observation point data
obs_reader = PflotranObservationPointReader("pflotran-obs-0.dat")
observations = obs_reader.read()

# Time series analysis
times = observations['time']
concentrations = observations['Tracer_Concentration']

import matplotlib.pyplot as plt
plt.plot(times, concentrations)
plt.xlabel('Time [years]')
plt.ylabel('Concentration [mol/L]')
plt.show()
```

### OpenFOAM Data

```python
from pydelling.readers import OpenFoamReader

# Read OpenFOAM case
reader = OpenFoamReader("case_directory/")
case_data = reader.read_time_series()

# Access specific fields
velocity = case_data.get_field('U', time=1000)
pressure = case_data.get_field('p', time=1000)

# Convert to VTK for analysis
reader.export_vtk("openfoam_results.vtk", time=1000)
```

## Writers

### HDF5 Output

```python
from pydelling.writers import PflotranHdf5CentroidWriter

# Prepare data for PFLOTRAN
writer = PflotranHdf5CentroidWriter("input_data.h5")

# Write centroid-based data
centroids = mesh.get_cell_centers()
permeability = calculate_permeability(mesh)
porosity = calculate_porosity(mesh)

writer.write_dataset('Coordinates', centroids)
writer.write_dataset('Permeability', permeability)
writer.write_dataset('Porosity', porosity)
```

### Raster Data

```python
from pydelling.writers import PflotranHdf5RasterWriter

# Create structured grid data for PFLOTRAN
writer = PflotranHdf5RasterWriter("structured_input.h5")

# Define grid
nx, ny, nz = 100, 50, 20
spacing = [1.0, 1.0, 0.5]  # meters

# Write structured data
writer.write_structured_grid(
    dimensions=(nx, ny, nz),
    spacing=spacing,
    origin=(0, 0, 0)
)

# Add material properties
permeability_field = generate_permeability_field(nx, ny, nz)
writer.write_field('Permeability', permeability_field)
```

## Preprocessing

### Mesh Preprocessing

```python
from pydelling.preprocessing import MeshPreprocessor

# Initialize preprocessor
preprocessor = MeshPreprocessor("input_mesh.msh")

# Clean and prepare mesh
preprocessor.remove_duplicates()
preprocessor.fix_orientation()
preprocessor.generate_boundaries()

# Apply transformations
preprocessor.scale(factor=0.001)  # mm to m conversion
preprocessor.translate(offset=[100, 200, 0])
preprocessor.rotate(axis='z', angle=45)

# Export processed mesh
preprocessor.export("processed_mesh.vtk")
```

### DFN (Discrete Fracture Network) Processing

```python
from pydelling.preprocessing import DfnPreprocessor

# Load fracture network
dfn = DfnPreprocessor("fracture_network.dat")

# Analyze network properties
connectivity = dfn.calculate_connectivity()
intersection_points = dfn.find_intersections()

print(f"Network contains {len(dfn.fractures)} fractures")
print(f"Average connectivity: {connectivity.mean():.2f}")

# Generate mesh for simulation
dfn.generate_simulation_mesh(
    mesh_size=0.5,
    output_file="dfn_mesh.msh"
)
```

### DFN Upscaling

```python
from pydelling.preprocessing import DfnUpscaler

# Initialize upscaler
upscaler = DfnUpscaler(
    dfn_file="detailed_fractures.dat",
    domain_size=(1000, 1000, 100)
)

# Perform upscaling
upscaler.calculate_equivalent_permeability(
    method='oda',  # or 'tensor'
    sample_size=100
)

# Generate upscaled properties
upscaled_k = upscaler.get_permeability_tensor()
upscaled_porosity = upscaler.get_effective_porosity()

# Export for continuum simulation
upscaler.export_continuum_properties("upscaled_properties.h5")
```

## Simulation Management

### PFLOTRAN Manager

```python
from pydelling.managers import PflotranManager

# Initialize manager
manager = PflotranManager(
    template_file="template.in",
    pflotran_executable="/path/to/pflotran"
)

# Define parameter variations
parameters = {
    'PERMEABILITY': [1e-12, 1e-13, 1e-14],  # m²
    'POROSITY': [0.1, 0.2, 0.3],
    'TEMPERATURE': [25, 50, 75]  # °C
}

# Run parameter study
results = manager.run_parameter_study(
    parameters=parameters,
    output_dir="parameter_study_results",
    n_cores=4
)

# Process results
for case, result in results.items():
    print(f"Case {case}: Final concentration = {result.final_concentration}")
```

### Remote HPC Execution

```python
from pydelling.managers import PflotranManager

# Configure for HPC
manager = PflotranManager(
    template_file="template.in",
    remote_config={
        'hostname': 'hpc.cluster.com',
        'username': 'user',
        'key_file': '~/.ssh/id_rsa',
        'work_dir': '/scratch/user/pflotran_runs',
        'queue_system': 'slurm',
        'partition': 'compute'
    }
)

# Submit batch jobs
job_ids = manager.submit_remote_jobs(
    parameters=parameters,
    nodes=2,
    cores_per_node=24,
    walltime='24:00:00'
)

# Monitor progress
manager.monitor_jobs(job_ids)
```

### COMSOL Manager

```python
from pydelling.managers import ComsolManager

# Initialize COMSOL manager
comsol = ComsolManager(
    comsol_executable="/path/to/comsol",
    license_server="license.server.com"
)

# Batch processing
mph_files = ["model1.mph", "model2.mph", "model3.mph"]
results = comsol.run_batch(mph_files, n_cores=8)

# Parametric sweep
sweep_params = {
    'param1': [1, 2, 3, 4, 5],
    'param2': [0.1, 0.2, 0.3]
}

sweep_results = comsol.run_parametric_sweep(
    "parametric_model.mph",
    parameters=sweep_params,
    output_dir="sweep_results"
)
```

## Postprocessing

### PFLOTRAN Postprocessing

```python
from pydelling.postprocessing import PflotranPostprocessor

# Initialize postprocessor
processor = PflotranPostprocessor("simulation_results/")

# Load time series data
processor.load_observation_points()
processor.load_mass_balance()

# Generate plots
processor.plot_breakthrough_curves(
    observation_points=['OBS-01', 'OBS-02'],
    species=['Tracer', 'U238'],
    output='breakthrough_curves.png'
)

# Create concentration maps
processor.create_concentration_maps(
    times=[0, 100, 500, 1000],  # years
    species='Tracer',
    output_dir='concentration_maps/'
)

# Export summary statistics
summary = processor.calculate_summary_statistics()
processor.export_summary('simulation_summary.xlsx')
```

### COMSOL Postprocessing

```python
from pydelling.postprocessing import ComsolPostprocessor

# Load COMSOL results
processor = ComsolPostprocessor("comsol_results.mph")

# Extract data
temperature_field = processor.extract_field('Temperature')
heat_flux = processor.extract_field('Heat Flux')

# Create visualizations
processor.create_contour_plot(
    field='Temperature',
    levels=20,
    output='temperature_contours.png'
)

# Generate reports
processor.generate_report(
    template='report_template.docx',
    output='simulation_report.pdf'
)
```

## Web Applications

### PFLOTRAN Manager Web Interface

```python
from pydelling.webapps import pflotran_manager_webapp

# Launch interactive web interface
app = pflotran_manager_webapp.create_app()

# Configure simulation parameters through web UI
app.run(
    host='localhost',
    port=8501,
    debug=True
)
```

Access the interface at `http://localhost:8501` to:
- Upload PFLOTRAN input files
- Define parameter ranges
- Monitor simulation progress
- Download results

### Sparse Interpolator Tool

```python
from pydelling.webapps import sparse_interpolator_webapp

# Launch interpolation tool
app = sparse_interpolator_webapp.create_app()
app.run(port=8502)
```

Features:
- Upload measurement data
- Configure interpolation parameters
- Preview interpolation results
- Export interpolated fields

## Advanced Workflows

### Multiphysics Coupling

```python
from pydelling.managers import PflotranManager, ComsolManager
from pydelling.utils import CouplingUtils

# Set up coupled simulation
pflotran = PflotranManager("flow_transport.in")
comsol = ComsolManager("heat_transfer.mph")

# Define coupling interface
coupler = CouplingUtils()

# Iterative coupling
for iteration in range(max_iterations):
    # Run flow/transport
    pflotran_results = pflotran.run()
    
    # Extract velocity field
    velocity = pflotran_results.extract_field('Velocity')
    
    # Pass to heat transfer
    comsol.set_parameter('velocity_field', velocity)
    comsol_results = comsol.run()
    
    # Extract temperature
    temperature = comsol_results.extract_field('Temperature')
    
    # Update PFLOTRAN properties
    pflotran.update_temperature_dependent_properties(temperature)
    
    # Check convergence
    if coupler.check_convergence(iteration):
        break
```

### Uncertainty Quantification

```python
from pydelling.estimators import MonteCarloEstimator
from pydelling.managers import PflotranManager

# Define uncertain parameters
uncertain_params = {
    'permeability': {
        'distribution': 'lognormal',
        'mean': 1e-13,
        'std': 0.5
    },
    'porosity': {
        'distribution': 'uniform',
        'min': 0.05,
        'max': 0.25
    }
}

# Monte Carlo analysis
mc_estimator = MonteCarloEstimator(
    model=PflotranManager("template.in"),
    parameters=uncertain_params,
    n_samples=1000
)

# Run uncertainty analysis
results = mc_estimator.run_analysis(
    output_quantities=['breakthrough_time', 'peak_concentration']
)

# Statistical analysis
mean_breakthrough = results['breakthrough_time'].mean()
std_breakthrough = results['breakthrough_time'].std()

print(f"Mean breakthrough time: {mean_breakthrough:.2f} ± {std_breakthrough:.2f} years")

# Sensitivity analysis
sensitivity = mc_estimator.calculate_sensitivity_indices()
mc_estimator.plot_sensitivity(output='sensitivity_analysis.png')
```

### Machine Learning Integration

```python
from pydelling.estimators import KDEEstimator
from pydelling.interpolation import SparseInterpolator
import numpy as np

# Load measurement data
measurements = load_field_data("borehole_data.csv")

# Kernel density estimation
kde = KDEEstimator()
kde.fit(measurements['coordinates'], measurements['permeability'])

# Generate realizations
n_realizations = 100
permeability_fields = []

for i in range(n_realizations):
    field = kde.sample_field(
        grid_points=mesh.get_cell_centers(),
        bandwidth='silverman'
    )
    permeability_fields.append(field)

# Sparse interpolation for large datasets
interpolator = SparseInterpolator(
    method='gaussian_process',
    kernel='matern'
)

interpolated_field = interpolator.interpolate(
    source_points=measurements['coordinates'],
    source_values=measurements['permeability'],
    target_points=mesh.get_cell_centers()
)
```

## Best Practices

### Performance Optimization

1. **Memory Management:**
   ```python
   # Process large datasets in chunks
   from pydelling.utils import chunk_processor
   
   for chunk in chunk_processor(large_dataset, chunk_size=1000):
       process_chunk(chunk)
   ```

2. **Parallel Processing:**
   ```python
   # Use multiprocessing for independent tasks
   from multiprocessing import Pool
   
   with Pool(n_cores) as pool:
       results = pool.map(simulation_function, parameter_sets)
   ```

3. **Efficient I/O:**
   ```python
   # Use HDF5 for large datasets
   import h5py
   
   with h5py.File('large_dataset.h5', 'r') as f:
       data = f['dataset'][start_idx:end_idx]  # Read only needed data
   ```

### Error Handling

```python
from pydelling.utils import PydellingError

try:
    reader = VTKReader("missing_file.vtk")
    data = reader.read()
except PydellingError as e:
    print(f"pydelling error: {e}")
    # Handle gracefully
except Exception as e:
    print(f"Unexpected error: {e}")
    # Log and report
```

### Logging

```python
import logging
from pydelling.utils import setup_logging

# Configure logging
setup_logging(level='INFO', log_file='pydelling.log')

logger = logging.getLogger('pydelling')
logger.info("Starting simulation workflow")
```

## Next Steps

- Explore specific module documentation in the API reference
- Check out the `code_snippets/` directory for more examples
- Join the pydelling community for support and discussions
- Consider contributing to the project

---

*Ready for more advanced topics? Check out the API reference documentation for detailed information about specific classes and methods.*

