# Examples and Code Snippets

This section provides practical examples and code snippets demonstrating common pydelling workflows. All examples are based on real-world use cases and can be found in the `code_snippets/` directory of the repository.

## Table of Contents

- [Getting Started Examples](#getting-started-examples)
- [Mesh Processing Workflows](#mesh-processing-workflows)
- [Simulation Management](#simulation-management)
- [Data Analysis and Visualization](#data-analysis-and-visualization)
- [Integration Examples](#integration-examples)
- [Advanced Workflows](#advanced-workflows)

## Getting Started Examples

### Basic Mesh Reading and Writing

```python
from pydelling.readers import VTKReader
from pydelling.writers import VTKWriter

# Read a mesh file
reader = VTKReader("input_mesh.vtk")
mesh_data = reader.read()

# Access mesh components
print(f"Number of points: {len(mesh_data['points'])}")
print(f"Number of cells: {len(mesh_data['cells']['triangle'])}")
print(f"Available point data: {list(mesh_data['point_data'].keys())}")

# Modify some data
mesh_data['cell_data']['material_id'] = [1] * len(mesh_data['cells']['triangle'])

# Write modified mesh
writer = VTKWriter("output_mesh.vtk")
writer.write(mesh_data)
print("Mesh processing completed!")
```

### Simple ConnectFlow Analysis

```python
from pydelling.readers import ConnectFlowReader
import matplotlib.pyplot as plt

# Read ConnectFlow output
reader = ConnectFlowReader("connectflow_output.dat")
data = reader.read()

# Extract flow data
flow_rates = data.get_flow_rates()
pressures = data.get_pressures()

# Basic visualization
plt.figure(figsize=(12, 5))

plt.subplot(1, 2, 1)
plt.hist(flow_rates, bins=50, alpha=0.7)
plt.xlabel('Flow Rate [m³/s]')
plt.ylabel('Frequency')
plt.title('Flow Rate Distribution')

plt.subplot(1, 2, 2)
plt.hist(pressures, bins=50, alpha=0.7, color='red')
plt.xlabel('Pressure [Pa]')
plt.ylabel('Frequency')
plt.title('Pressure Distribution')

plt.tight_layout()
plt.savefig('connectflow_analysis.png')
plt.show()
```

## Mesh Processing Workflows

### Complete Mesh Preprocessing Pipeline

```python
from pydelling.preprocessing import MeshPreprocessor
from pydelling.readers import VTKReader
from pydelling.writers import PflotranHdf5CentroidWriter
import numpy as np

def complete_mesh_pipeline(input_file, output_file):
    """Complete mesh preprocessing pipeline."""
    
    # Step 1: Read and validate input
    print("Reading input mesh...")
    reader = VTKReader(input_file)
    mesh = reader.read()
    
    # Step 2: Initialize preprocessor
    processor = MeshPreprocessor(mesh)
    
    # Step 3: Cleaning operations
    print("Cleaning mesh...")
    processor.remove_duplicate_points(tolerance=1e-6)
    processor.remove_degenerate_cells()
    processor.fix_cell_orientation()
    
    # Step 4: Unit conversion (assuming input in mm)
    print("Converting units...")
    processor.scale(factor=0.001)  # mm to m
    
    # Step 5: Generate material properties
    print("Assigning material properties...")
    centroids = processor.get_cell_centroids()
    n_cells = len(centroids)
    
    # Example: depth-dependent permeability
    depths = centroids[:, 2]  # z-coordinates
    permeability = 1e-12 * np.exp(-depths / 100)  # exponential decay with depth
    porosity = 0.3 * np.ones(n_cells)  # constant porosity
    
    # Step 6: Write simulation input
    print("Writing PFLOTRAN input...")
    writer = PflotranHdf5CentroidWriter(output_file)
    writer.write_coordinates(centroids)
    writer.write_dataset('Permeability', permeability)
    writer.write_dataset('Porosity', porosity)
    writer.close()
    
    print(f"Pipeline completed: {input_file} -> {output_file}")
    return {
        'n_cells': n_cells,
        'permeability_range': (permeability.min(), permeability.max()),
        'porosity_range': (porosity.min(), porosity.max())
    }

# Run the pipeline
if __name__ == "__main__":
    results = complete_mesh_pipeline("raw_mesh.vtk", "simulation_input.h5")
    print(f"Processed {results['n_cells']} cells")
    print(f"Permeability range: {results['permeability_range'][0]:.2e} - {results['permeability_range'][1]:.2e} m²")
```

### DFN Processing Example

See `code_snippets/connectflow_mesh/read_connectflow_mesh.py`:

```python
from pydelling.readers import ConnectFlowMeshReader
from pydelling.preprocessing import DfnPreprocessor
from pydelling.writers import VTKWriter

# Read ConnectFlow mesh
reader = ConnectFlowMeshReader("dummy_cf_2cell_mesh.msh")
mesh_data = reader.read()

# Initialize DFN preprocessor
dfn = DfnPreprocessor(mesh_data)

# Analyze fracture network
network_stats = dfn.analyze_network()
print(f"Network statistics:")
print(f"  Number of fractures: {network_stats['n_fractures']}")
print(f"  Total fracture area: {network_stats['total_area']:.2f} m²")
print(f"  Average fracture size: {network_stats['avg_size']:.2f} m²")
print(f"  Network connectivity: {network_stats['connectivity']:.3f}")

# Find fracture intersections
intersections = dfn.find_intersections()
print(f"Found {len(intersections)} fracture intersections")

# Export processed network
writer = VTKWriter("processed_dfn.vtk")
writer.write(dfn.get_processed_mesh())

# Generate mesh for simulation
dfn.generate_simulation_mesh(
    mesh_size=0.5,
    output_file="dfn_simulation_mesh.msh"
)
```

## Simulation Management

### PFLOTRAN Parameter Study

```python
from pydelling.managers import PflotranManager
import numpy as np
import pandas as pd

def run_permeability_study():
    """Run a parameter study varying permeability values."""
    
    # Initialize PFLOTRAN manager
    manager = PflotranManager(
        template_file="template.in",
        pflotran_executable="/usr/local/bin/pflotran"
    )
    
    # Define parameter variations
    permeability_values = np.logspace(-15, -11, 9)  # 1e-15 to 1e-11 m²
    
    parameters = {
        'PERMEABILITY': permeability_values.tolist()
    }
    
    # Run parameter study
    print("Starting parameter study...")
    results = manager.run_parameter_study(
        parameters=parameters,
        output_dir="permeability_study",
        n_cores=4,
        cleanup_individual_runs=False
    )
    
    # Process results
    summary_data = []
    for case_name, result in results.items():
        # Extract key metrics
        breakthrough_time = result.get_breakthrough_time(threshold=0.5)
        peak_concentration = result.get_peak_concentration()
        total_mass = result.get_total_mass_discharged()
        
        summary_data.append({
            'case': case_name,
            'permeability': result.parameters['PERMEABILITY'],
            'breakthrough_time': breakthrough_time,
            'peak_concentration': peak_concentration,
            'total_mass': total_mass
        })
    
    # Create summary dataframe
    df = pd.DataFrame(summary_data)
    df.to_csv("permeability_study_summary.csv", index=False)
    
    # Plot results
    import matplotlib.pyplot as plt
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    # Breakthrough time vs permeability
    axes[0].loglog(df['permeability'], df['breakthrough_time'], 'o-')
    axes[0].set_xlabel('Permeability [m²]')
    axes[0].set_ylabel('Breakthrough Time [years]')
    axes[0].set_title('Breakthrough Time vs Permeability')
    
    # Peak concentration vs permeability
    axes[1].semilogx(df['permeability'], df['peak_concentration'], 'o-', color='red')
    axes[1].set_xlabel('Permeability [m²]')
    axes[1].set_ylabel('Peak Concentration [mol/L]')
    axes[1].set_title('Peak Concentration vs Permeability')
    
    # Total mass vs permeability
    axes[2].loglog(df['permeability'], df['total_mass'], 'o-', color='green')
    axes[2].set_xlabel('Permeability [m²]')
    axes[2].set_ylabel('Total Mass Discharged [mol]')
    axes[2].set_title('Total Mass vs Permeability')
    
    plt.tight_layout()
    plt.savefig('permeability_study_results.png', dpi=300)
    plt.show()
    
    return df

# Run the study
if __name__ == "__main__":
    results_df = run_permeability_study()
    print(f"Study completed with {len(results_df)} cases")
```

### Remote HPC Execution

```python
from pydelling.managers import PflotranManager
import time

def submit_hpc_jobs():
    """Submit PFLOTRAN jobs to HPC cluster."""
    
    # Configure for HPC
    manager = PflotranManager(
        template_file="large_scale_template.in",
        remote_config={
            'hostname': 'hpc.cluster.edu',
            'username': 'researcher',
            'key_file': '~/.ssh/id_rsa_hpc',
            'work_dir': '/scratch/researcher/pflotran_runs',
            'queue_system': 'slurm',
            'partition': 'compute',
            'modules': ['pflotran/3.0.2', 'hdf5/1.12.0']
        }
    )
    
    # Define large parameter space
    parameters = {
        'PERMEABILITY': [1e-14, 5e-14, 1e-13, 5e-13, 1e-12],
        'POROSITY': [0.1, 0.2, 0.3],
        'INJECTION_RATE': [0.001, 0.01, 0.1]  # m³/s
    }
    
    # Submit batch jobs
    print("Submitting jobs to HPC...")
    job_ids = manager.submit_remote_jobs(
        parameters=parameters,
        nodes=2,
        cores_per_node=24,
        memory_per_node='64GB',
        walltime='48:00:00',
        job_name_prefix='pflotran_param_study'
    )
    
    print(f"Submitted {len(job_ids)} jobs:")
    for job_id in job_ids:
        print(f"  Job ID: {job_id}")
    
    # Monitor job progress
    print("Monitoring job progress...")
    while True:
        status = manager.check_job_status(job_ids)
        
        running = sum(1 for s in status.values() if s == 'RUNNING')
        completed = sum(1 for s in status.values() if s == 'COMPLETED')
        failed = sum(1 for s in status.values() if s == 'FAILED')
        
        print(f"Jobs - Running: {running}, Completed: {completed}, Failed: {failed}")
        
        if completed + failed == len(job_ids):
            break
            
        time.sleep(300)  # Check every 5 minutes
    
    # Download results
    if completed > 0:
        print("Downloading results...")
        results = manager.download_results(job_ids)
        manager.create_summary_report(results, "hpc_study_summary.html")
        print("HPC study completed successfully")
    
    if failed > 0:
        print(f"Warning: {failed} jobs failed")
        failed_jobs = [jid for jid, status in status.items() if status == 'FAILED']
        manager.diagnose_failed_jobs(failed_jobs)

# Run HPC submission
if __name__ == "__main__":
    submit_hpc_jobs()
```

## Data Analysis and Visualization

### PFLOTRAN Output Analysis

```python
from pydelling.readers import PflotranObservationPointReader
from pydelling.postprocessing import PflotranPostprocessor
import matplotlib.pyplot as plt
import numpy as np

def analyze_pflotran_results(case_directory):
    """Comprehensive analysis of PFLOTRAN simulation results."""
    
    # Initialize postprocessor
    processor = PflotranPostprocessor(case_directory)
    
    # Load observation point data
    obs_files = processor.find_observation_files()
    print(f"Found {len(obs_files)} observation point files")
    
    # Analysis for each observation point
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    for i, obs_file in enumerate(obs_files[:4]):  # Plot first 4 points
        reader = PflotranObservationPointReader(obs_file)
        data = reader.read()
        
        ax = axes[i//2, i%2]
        
        # Plot concentration vs time
        ax.plot(data['Time [y]'], data['Tracer Concentration [M]'], 'b-', linewidth=2)
        ax.set_xlabel('Time [years]')
        ax.set_ylabel('Concentration [mol/L]')
        ax.set_title(f'Observation Point {i+1}')
        ax.grid(True, alpha=0.3)
        ax.set_yscale('log')
        
        # Calculate and annotate peak
        peak_idx = np.argmax(data['Tracer Concentration [M]'])
        peak_time = data['Time [y]'][peak_idx]
        peak_conc = data['Tracer Concentration [M]'][peak_idx]
        
        ax.annotate(f'Peak: {peak_conc:.2e} M\n@ {peak_time:.1f} years',
                   xy=(peak_time, peak_conc),
                   xytext=(peak_time*1.5, peak_conc*0.5),
                   arrowprops=dict(arrowstyle='->', color='red'),
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
    
    plt.tight_layout()
    plt.savefig('breakthrough_curves.png', dpi=300)
    plt.show()
    
    # Mass balance analysis
    mass_balance = processor.analyze_mass_balance()
    
    print("\nMass Balance Analysis:")
    print(f"  Total injected mass: {mass_balance['total_injected']:.2e} mol")
    print(f"  Total extracted mass: {mass_balance['total_extracted']:.2e} mol")
    print(f"  Mass in domain: {mass_balance['mass_in_domain']:.2e} mol")
    print(f"  Mass balance error: {mass_balance['balance_error']:.2f}%")
    
    # Create concentration contour maps
    processor.create_concentration_maps(
        times=[1, 10, 50, 100, 500],
        output_dir='concentration_maps',
        species='Tracer',
        log_scale=True
    )
    
    return processor

# Run analysis
if __name__ == "__main__":
    results = analyze_pflotran_results("simulation_output/")
    print("Analysis completed")
```

### Mesh Quality Assessment

```python
from pydelling.readers import VTKReader
from pydelling.preprocessing import MeshQualityAnalyzer
import matplotlib.pyplot as plt
import numpy as np

def assess_mesh_quality(mesh_file):
    """Comprehensive mesh quality assessment."""
    
    # Read mesh
    reader = VTKReader(mesh_file)
    mesh = reader.read()
    
    # Initialize quality analyzer
    analyzer = MeshQualityAnalyzer(mesh)
    
    # Calculate quality metrics
    quality_metrics = analyzer.calculate_all_metrics()
    
    # Create quality report
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    axes = axes.flatten()
    
    metrics = [
        ('aspect_ratio', 'Aspect Ratio', 'linear'),
        ('skewness', 'Skewness', 'linear'),
        ('jacobian', 'Jacobian', 'linear'),
        ('min_angle', 'Minimum Angle [°]', 'linear'),
        ('max_angle', 'Maximum Angle [°]', 'linear'),
        ('volume', 'Cell Volume', 'log')
    ]
    
    for i, (metric, title, scale) in enumerate(metrics):
        if metric in quality_metrics:
            values = quality_metrics[metric]
            
            axes[i].hist(values, bins=50, alpha=0.7, edgecolor='black')
            axes[i].set_xlabel(title)
            axes[i].set_ylabel('Number of Cells')
            axes[i].set_title(f'{title} Distribution')
            axes[i].grid(True, alpha=0.3)
            
            if scale == 'log':
                axes[i].set_xscale('log')
            
            # Add statistics
            mean_val = np.mean(values)
            std_val = np.std(values)
            axes[i].axvline(mean_val, color='red', linestyle='--', 
                           label=f'Mean: {mean_val:.3f}')
            axes[i].legend()
    
    plt.tight_layout()
    plt.savefig('mesh_quality_analysis.png', dpi=300)
    plt.show()
    
    # Print summary statistics
    print("Mesh Quality Summary:")
    print(f"  Total cells: {len(mesh['cells']['triangle'])}")
    
    for metric, title, _ in metrics:
        if metric in quality_metrics:
            values = quality_metrics[metric]
            print(f"  {title}:")
            print(f"    Mean: {np.mean(values):.3f}")
            print(f"    Std:  {np.std(values):.3f}")
            print(f"    Min:  {np.min(values):.3f}")
            print(f"    Max:  {np.max(values):.3f}")
    
    # Identify problem elements
    problem_elements = analyzer.identify_problem_elements(
        aspect_ratio_threshold=100,
        skewness_threshold=0.95,
        min_angle_threshold=5
    )
    
    if problem_elements:
        print(f"\nFound {len(problem_elements)} problematic elements")
        analyzer.export_problem_elements("problem_elements.vtk")
    else:
        print("\nNo problematic elements found")
    
    return quality_metrics

# Run quality assessment
if __name__ == "__main__":
    quality_results = assess_mesh_quality("mesh_to_analyze.vtk")
```

## Integration Examples

### Multi-Physics Coupling

```python
from pydelling.managers import PflotranManager, ComsolManager
from pydelling.utils import CouplingInterface
import numpy as np

def coupled_flow_heat_simulation():
    """Example of coupled flow-heat transport simulation."""
    
    # Initialize managers
    flow_manager = PflotranManager("flow_template.in")
    heat_manager = ComsolManager("heat_transfer.mph")
    
    # Set up coupling interface
    coupler = CouplingInterface(
        primary_solver=flow_manager,
        secondary_solver=heat_manager,
        coupling_fields=['velocity', 'temperature']
    )
    
    # Coupling parameters
    max_iterations = 10
    convergence_tolerance = 1e-4
    under_relaxation = 0.7
    
    # Initial conditions
    temperature_field = 25.0 * np.ones(1000)  # Initial temperature [°C]
    
    print("Starting coupled simulation...")
    
    for outer_iter in range(max_iterations):
        print(f"Coupling iteration {outer_iter + 1}/{max_iterations}")
        
        # Step 1: Run flow simulation with current temperature
        flow_manager.set_temperature_field(temperature_field)
        flow_results = flow_manager.run()
        
        # Step 2: Extract velocity field
        velocity_field = flow_results.get_velocity_field()
        
        # Step 3: Run heat transport with updated velocity
        heat_manager.set_velocity_field(velocity_field)
        heat_results = heat_manager.run()
        
        # Step 4: Extract updated temperature
        new_temperature = heat_results.get_temperature_field()
        
        # Step 5: Check convergence
        temp_change = np.max(np.abs(new_temperature - temperature_field))
        print(f"  Maximum temperature change: {temp_change:.6f} °C")
        
        if temp_change < convergence_tolerance:
            print("Coupling converged!")
            break
        
        # Step 6: Apply under-relaxation
        temperature_field = (under_relaxation * new_temperature + 
                           (1 - under_relaxation) * temperature_field)
    
    else:
        print("Warning: Coupling did not converge within maximum iterations")
    
    # Export final results
    coupler.export_coupled_results("coupled_results.vtk")
    
    return {
        'converged': temp_change < convergence_tolerance,
        'iterations': outer_iter + 1,
        'final_temp_range': (temperature_field.min(), temperature_field.max()),
        'final_velocity_magnitude': np.linalg.norm(velocity_field, axis=1).max()
    }

# Run coupled simulation
if __name__ == "__main__":
    results = coupled_flow_heat_simulation()
    print(f"Coupling results: {results}")
```

## Advanced Workflows

### Uncertainty Quantification

```python
from pydelling.estimators import MonteCarloEstimator
from pydelling.managers import PflotranManager
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

def uncertainty_quantification_study():
    """Monte Carlo uncertainty quantification example."""
    
    # Define uncertain parameters
    uncertain_params = {
        'permeability': {
            'distribution': 'lognormal',
            'loc': np.log(1e-13),  # log-mean
            'scale': 0.5,          # log-std
            'description': 'Intrinsic permeability [m²]'
        },
        'porosity': {
            'distribution': 'uniform',
            'loc': 0.1,   # minimum
            'scale': 0.2,  # range (max - min)
            'description': 'Porosity [-]'
        },
        'dispersivity': {
            'distribution': 'gamma',
            'a': 2,        # shape
            'scale': 0.5,  # scale
            'description': 'Longitudinal dispersivity [m]'
        }
    }
    
    # Initialize Monte Carlo estimator
    mc_estimator = MonteCarloEstimator(
        model=PflotranManager("uncertainty_template.in"),
        parameters=uncertain_params,
        n_samples=500
    )
    
    # Define output quantities of interest
    output_quantities = [
        'breakthrough_time_50percent',
        'peak_concentration',
        'total_mass_recovered',
        'plume_extent_x',
        'plume_extent_y'
    ]
    
    print("Running Monte Carlo uncertainty analysis...")
    results = mc_estimator.run_analysis(
        output_quantities=output_quantities,
        n_cores=8,
        save_intermediate=True
    )
    
    # Statistical analysis
    print("\nUncertainty Analysis Results:")
    print("=" * 50)
    
    statistics = {}
    for qty in output_quantities:
        values = results[qty]
        statistics[qty] = {
            'mean': np.mean(values),
            'std': np.std(values),
            'min': np.min(values),
            'max': np.max(values),
            'p5': np.percentile(values, 5),
            'p95': np.percentile(values, 95)
        }
        
        print(f"{qty}:")
        print(f"  Mean ± Std: {statistics[qty]['mean']:.3f} ± {statistics[qty]['std']:.3f}")
        print(f"  Range: [{statistics[qty]['min']:.3f}, {statistics[qty]['max']:.3f}]")
        print(f"  90% CI: [{statistics[qty]['p5']:.3f}, {statistics[qty]['p95']:.3f}]")
        print()
    
    # Visualization
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    axes = axes.flatten()
    
    for i, qty in enumerate(output_quantities):
        if i < len(axes):
            values = results[qty]
            
            # Histogram with fitted normal distribution
            axes[i].hist(values, bins=30, density=True, alpha=0.7, 
                        color='skyblue', edgecolor='black')
            
            # Fit and plot normal distribution
            mu, sigma = stats.norm.fit(values)
            x_range = np.linspace(values.min(), values.max(), 100)
            axes[i].plot(x_range, stats.norm.pdf(x_range, mu, sigma), 
                        'r-', linewidth=2, label=f'Normal fit (μ={mu:.3f}, σ={sigma:.3f})')
            
            axes[i].set_xlabel(qty.replace('_', ' ').title())
            axes[i].set_ylabel('Probability Density')
            axes[i].set_title(f'Distribution of {qty.replace("_", " ").title()}')
            axes[i].legend()
            axes[i].grid(True, alpha=0.3)
    
    # Remove empty subplot
    if len(output_quantities) < len(axes):
        fig.delaxes(axes[-1])
    
    plt.tight_layout()
    plt.savefig('uncertainty_distributions.png', dpi=300)
    plt.show()
    
    # Sensitivity analysis
    sensitivity_indices = mc_estimator.calculate_sobol_indices(
        output_quantities=output_quantities
    )
    
    print("Sensitivity Analysis (Sobol Indices):")
    print("=" * 40)
    
    for qty in output_quantities:
        print(f"{qty}:")
        for param in uncertain_params.keys():
            s1 = sensitivity_indices[qty]['S1'][param]
            st = sensitivity_indices[qty]['ST'][param]
            print(f"  {param}: S1={s1:.3f}, ST={st:.3f}")
        print()
    
    # Export results
    import pandas as pd
    
    # Create results dataframe
    results_df = pd.DataFrame(results)
    results_df.to_csv('uncertainty_results.csv', index=False)
    
    # Create summary statistics dataframe
    stats_df = pd.DataFrame(statistics).T
    stats_df.to_csv('uncertainty_statistics.csv')
    
    print("Uncertainty quantification completed successfully!")
    
    return results, statistics, sensitivity_indices

# Run uncertainty quantification
if __name__ == "__main__":
    mc_results, stats, sensitivity = uncertainty_quantification_study()
```

## Running the Examples

### Prerequisites

Make sure you have pydelling installed and properly configured:

```bash
# Install pydelling
uv sync

# Verify installation
python -c "import pydelling; print(f'pydelling {pydelling.__version__} ready!')"
```

### Running Individual Examples

Each example can be run independently:

```bash
# Basic mesh processing
cd code_snippets/
python mesh_processing_example.py

# ConnectFlow analysis  
cd connectflow_mesh/
python read_connectflow_mesh.py

# Parameter study
cd simulation_management/
python pflotran_parameter_study.py
```

### Modifying Examples

All examples are designed to be easily modified:

1. **Change input files**: Update file paths to match your data
2. **Adjust parameters**: Modify analysis parameters for your specific case
3. **Add custom processing**: Extend examples with your own analysis steps
4. **Scale up/down**: Adjust computational parameters for your system

### Example Data

Sample data files for testing examples can be found in:
- `code_snippets/connectflow_mesh/dummy_cf_2cell_mesh.msh`
- `code_snippets/feflow_reader/c_layer_b_tf.dat`
- Various test datasets in the `pydelling/tests/` directory

---

*For more advanced examples and tutorials, see the [Tutorials](tutorials.md) section.*