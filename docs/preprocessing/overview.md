# Preprocessing Overview

pydelling's preprocessing module provides comprehensive tools for preparing and manipulating mesh data, discrete fracture networks (DFN), and geometric data for numerical simulations.

## Key Components

### Mesh Preprocessing

| Tool | Purpose | Input Formats | Key Features |
|------|---------|---------------|--------------|
| **MeshPreprocessor** | General mesh operations | VTK, MSH, STL | Cleaning, repair, transformation |
| **ClosedStlGenerator** | STL surface processing | STL | Closure, manifold repair |
| **GiDPreprocessor** | GiD mesh handling | GiD formats | Boundary conditions, materials |

### DFN (Discrete Fracture Network) Processing

| Tool | Purpose | Applications | Capabilities |
|------|---------|--------------|-------------|
| **DfnPreprocessor** | DFN data processing | Fracture networks | Network analysis, mesh generation |
| **DfnUpscaler** | Scale-dependent modeling | Multiscale studies | Equivalent properties, upscaling |

### Specialized Processors

| Tool | Purpose | Use Cases | Output |
|------|---------|-----------|---------|
| **StructuredGridProcessor** | Regular grid operations | Structured simulations | Grid generation, refinement |
| **BoundaryProcessor** | Boundary condition setup | Complex geometries | BC assignment, validation |

## Common Workflows

### Basic Mesh Preprocessing

```python
from pydelling.preprocessing import MeshPreprocessor

# Initialize with mesh file
processor = MeshPreprocessor("input_mesh.msh")

# Basic cleaning operations
processor.remove_duplicate_points(tolerance=1e-6)
processor.remove_degenerate_cells()
processor.fix_cell_orientation()

# Geometric transformations
processor.scale(factor=0.001)  # mm to m conversion
processor.translate(offset=[10, 20, 0])
processor.rotate(axis='z', angle=45)  # degrees

# Export processed mesh
processor.export("cleaned_mesh.vtk")
```

### STL Surface Processing

```python
from pydelling.preprocessing import ClosedStlGenerator

# Load STL surface
stl_processor = ClosedStlGenerator("open_surface.stl")

# Analyze surface
is_closed = stl_processor.check_closed()
print(f"Surface is closed: {is_closed}")

# Repair if needed
if not is_closed:
    stl_processor.fill_holes(hole_size_limit=10.0)
    stl_processor.fix_normals()
    
# Generate closed surface
closed_surface = stl_processor.generate_closed_surface()
stl_processor.save("closed_surface.stl")
```

### DFN Preprocessing

```python
from pydelling.preprocessing import DfnPreprocessor

# Load fracture network
dfn = DfnPreprocessor("fracture_network.dat")

# Analyze network properties
stats = dfn.calculate_network_statistics()
print(f"Number of fractures: {stats['n_fractures']}")
print(f"Total fracture area: {stats['total_area']:.2f} m²")
print(f"Network connectivity: {stats['connectivity']:.3f}")

# Find intersections
intersections = dfn.find_fracture_intersections()
print(f"Found {len(intersections)} intersection lines")

# Generate computational mesh
dfn.generate_mesh(
    mesh_size=0.5,
    feature_angle=30,
    output_file="dfn_mesh.msh"
)
```

## Advanced Features

### Adaptive Mesh Refinement

```python
from pydelling.preprocessing import AdaptiveMeshRefiner

# Initialize with base mesh
refiner = AdaptiveMeshRefiner("base_mesh.vtk")

# Define refinement criteria
def refinement_criterion(cell):
    # Refine based on gradient
    gradient_magnitude = calculate_gradient(cell)
    return gradient_magnitude > threshold

# Apply adaptive refinement
refiner.set_refinement_criterion(refinement_criterion)
refiner.refine(max_levels=3)

# Export refined mesh
refined_mesh = refiner.get_refined_mesh()
refiner.export("refined_mesh.vtk")
```

### Multi-material Processing

```python
from pydelling.preprocessing import MultiMaterialProcessor

# Load mesh with material information
processor = MultiMaterialProcessor("mesh_with_materials.vtk")

# Assign materials based on regions
processor.assign_material_by_region(
    region_bounds={'x': (0, 100), 'y': (0, 50), 'z': (0, 20)},
    material_id=1,
    material_properties={'permeability': 1e-12, 'porosity': 0.3}
)

# Assign materials from STL boundaries
processor.assign_material_from_stl(
    stl_file="material_boundary.stl",
    material_id=2,
    inside_properties={'permeability': 1e-15, 'porosity': 0.1}
)

# Smooth material transitions
processor.smooth_material_interfaces(smoothing_radius=2.0)
```

### Boundary Condition Assignment

```python
from pydelling.preprocessing import BoundaryProcessor

# Initialize boundary processor
bc_processor = BoundaryProcessor("mesh.vtk")

# Identify boundary faces
boundary_faces = bc_processor.identify_boundaries()

# Assign boundary conditions by location
bc_processor.assign_bc_by_location(
    location='xmin',
    bc_type='dirichlet',
    value=1000.0,  # pressure in Pa
    variable='pressure'
)

bc_processor.assign_bc_by_location(
    location='xmax',
    bc_type='neumann',
    value=0.0,  # no flow
    variable='pressure'
)

# Export with boundary information
bc_processor.export("mesh_with_bc.vtk")
```

## DFN-Specific Tools

### Network Analysis

```python
from pydelling.preprocessing import DfnAnalyzer

analyzer = DfnAnalyzer("fracture_network.dat")

# Geometric analysis
length_distribution = analyzer.get_length_distribution()
orientation_analysis = analyzer.get_orientation_statistics()
spacing_analysis = analyzer.get_spacing_statistics()

# Topological analysis
connectivity_map = analyzer.build_connectivity_graph()
clusters = analyzer.identify_connected_clusters()
backbone = analyzer.extract_backbone_network()

# Export analysis results
analyzer.export_statistics("dfn_analysis.xlsx")
analyzer.plot_rose_diagram("fracture_orientations.png")
```

### DFN Upscaling

```python
from pydelling.preprocessing import DfnUpscaler

upscaler = DfnUpscaler(
    dfn_file="detailed_fractures.dat",
    domain_size=(1000, 1000, 100),  # meters
    block_size=(10, 10, 5)          # upscaling block size
)

# Calculate equivalent permeability
upscaler.calculate_equivalent_permeability(
    method='flow_based',  # or 'geometric', 'oda'
    boundary_conditions='periodic',
    pressure_gradient=[1, 0, 0]
)

# Generate upscaled properties
equivalent_k = upscaler.get_permeability_tensor()
equivalent_porosity = upscaler.get_effective_porosity()

# Create continuum representation
upscaler.generate_continuum_mesh(
    grid_resolution=(100, 100, 20),
    output_file="upscaled_domain.vtk"
)

# Export upscaled properties for simulation
upscaler.export_pflotran_input("upscaled_properties.h5")
```

## Integration Examples

### Complete Preprocessing Pipeline

```python
from pydelling.preprocessing import (
    MeshPreprocessor, 
    BoundaryProcessor,
    MaterialAssigner
)
from pydelling.writers import PflotranHdf5CentroidWriter

# Step 1: Basic mesh preprocessing
mesh_proc = MeshPreprocessor("raw_mesh.msh")
mesh_proc.clean_mesh()
mesh_proc.apply_unit_conversion(scale_factor=0.001)  # mm to m
cleaned_mesh = mesh_proc.get_mesh()

# Step 2: Boundary condition assignment
bc_proc = BoundaryProcessor(cleaned_mesh)
bc_proc.auto_detect_boundaries()
bc_proc.assign_boundary_conditions_from_config("bc_config.yaml")

# Step 3: Material assignment
material_proc = MaterialAssigner(cleaned_mesh)
material_proc.assign_materials_from_regions("material_regions.json")

# Step 4: Export for simulation
writer = PflotranHdf5CentroidWriter("simulation_input.h5")
final_mesh = material_proc.get_mesh()

writer.write_coordinates(final_mesh.get_centroids())
writer.write_dataset('MaterialID', final_mesh.get_material_ids())
writer.write_dataset('Permeability', final_mesh.get_permeabilities())
writer.write_dataset('Porosity', final_mesh.get_porosities())
writer.close()

print("Preprocessing pipeline completed successfully")
```

### DFN to Continuum Workflow

```python
from pydelling.preprocessing import DfnPreprocessor, DfnUpscaler
from pydelling.writers import PflotranHdf5RasterWriter

# Process DFN
dfn_proc = DfnPreprocessor("fracture_network.dat")
dfn_proc.validate_network()
dfn_proc.remove_isolated_fractures()

# Upscale to continuum
upscaler = DfnUpscaler(dfn_proc.get_network())
upscaler.set_upscaling_parameters(
    block_size=(5, 5, 2),
    overlap_ratio=0.1,
    method='percolation'
)

upscaled_properties = upscaler.run_upscaling()

# Generate structured grid
grid_writer = PflotranHdf5RasterWriter("continuum_input.h5")
grid_writer.write_structured_grid(
    dimensions=(200, 100, 50),
    spacing=(1.0, 1.0, 0.5),
    origin=(0, 0, 0)
)

# Write upscaled properties
grid_writer.write_field('Permeability_XX', upscaled_properties['kxx'])
grid_writer.write_field('Permeability_YY', upscaled_properties['kyy'])
grid_writer.write_field('Permeability_ZZ', upscaled_properties['kzz'])
grid_writer.write_field('Porosity', upscaled_properties['porosity'])
grid_writer.close()
```

## Quality Assurance

### Mesh Quality Metrics

```python
from pydelling.preprocessing import MeshQualityAnalyzer

analyzer = MeshQualityAnalyzer("processed_mesh.vtk")

# Calculate quality metrics
quality_report = analyzer.generate_quality_report()
print(f"Minimum angle: {quality_report['min_angle']:.2f}°")
print(f"Maximum aspect ratio: {quality_report['max_aspect_ratio']:.2f}")
print(f"Skewness (average): {quality_report['avg_skewness']:.3f}")

# Identify problematic elements
bad_elements = analyzer.find_poor_quality_elements(
    min_angle_threshold=10,
    max_aspect_ratio_threshold=100,
    max_skewness_threshold=0.95
)

if bad_elements:
    print(f"Found {len(bad_elements)} poor quality elements")
    analyzer.export_problem_elements("problem_elements.vtk")
```

### Validation Tools

```python
from pydelling.preprocessing import MeshValidator

validator = MeshValidator("mesh_to_validate.vtk")

# Run comprehensive validation
validation_results = validator.run_full_validation()

for check, result in validation_results.items():
    status = "PASS" if result['passed'] else "FAIL"
    print(f"{check}: {status}")
    if not result['passed']:
        print(f"  Issues: {result['issues']}")

# Auto-fix common issues
if not validation_results['manifold_check']['passed']:
    validator.fix_non_manifold_edges()

if not validation_results['orientation_check']['passed']:
    validator.fix_inconsistent_orientation()
```

## Performance Optimization

### Large Mesh Processing

```python
from pydelling.preprocessing import LargeMeshProcessor

# Initialize for out-of-core processing
processor = LargeMeshProcessor(
    "very_large_mesh.vtk",
    memory_limit='8GB',
    temp_dir='/tmp/pydelling'
)

# Process in chunks
processor.enable_chunked_processing(chunk_size=100000)

# Apply operations
processor.remove_duplicates()
processor.scale(0.001)

# Save processed mesh
processor.export("processed_large_mesh.vtk")
```

### Parallel Processing

```python
from pydelling.preprocessing import ParallelMeshProcessor
from multiprocessing import Pool

def process_mesh_chunk(chunk_data):
    chunk_processor = MeshPreprocessor()
    return chunk_processor.process_chunk(chunk_data)

# Divide mesh into chunks
mesh_chunks = divide_mesh_into_chunks("large_mesh.vtk", n_chunks=8)

# Process chunks in parallel
with Pool(processes=8) as pool:
    processed_chunks = pool.map(process_mesh_chunk, mesh_chunks)

# Merge results
final_mesh = merge_processed_chunks(processed_chunks)
```

## Best Practices

### Data Preservation

```python
# Always backup original data
import shutil
shutil.copy("original_mesh.vtk", "original_mesh_backup.vtk")

# Use version control for processed meshes
processor = MeshPreprocessor("original_mesh.vtk")
processor.save_processing_log("processing_log.json")
```

### Parameter Documentation

```python
# Document processing parameters
processing_config = {
    'duplicate_tolerance': 1e-6,
    'scale_factor': 0.001,
    'rotation_angle': 45,
    'translation_vector': [10, 20, 0],
    'processed_date': datetime.now().isoformat(),
    'pydelling_version': pydelling.__version__
}

# Save configuration with output
with open("processing_config.json", "w") as f:
    json.dump(processing_config, f, indent=2)
```

### Error Handling

```python
from pydelling.preprocessing import MeshPreprocessor
from pydelling.utils import PydellingError

try:
    processor = MeshPreprocessor("input_mesh.vtk")
    processor.validate_input()
    processed_mesh = processor.process()
    
except PydellingError as e:
    print(f"Preprocessing error: {e}")
    # Handle pydelling-specific errors
    
except Exception as e:
    print(f"Unexpected error: {e}")
    # Handle other errors
    
finally:
    # Cleanup temporary files
    processor.cleanup_temp_files()
```

## Troubleshooting

### Common Issues

1. **Memory limitations**
   - Use chunked processing
   - Enable out-of-core operations
   - Reduce precision if appropriate

2. **Geometric degeneracies**
   - Increase tolerance values
   - Use robust geometric predicates
   - Apply mesh repair operations

3. **File format issues**
   - Verify input file format
   - Check for corrupted data
   - Use format-specific readers

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable detailed preprocessing logging
processor = MeshPreprocessor("debug_mesh.vtk", debug_mode=True)
processor.enable_verbose_output()
```

---

*For detailed information about specific preprocessing tools, see the individual pages in this section.*