# Release Notes

This document tracks the development history and evolution of pydelling, highlighting major features, improvements, and bug fixes in each version.

## Version 1.2.0

- Introduce `pydelling.assets` with versioned preview contracts, PFLOTRAN case handlers, and a packaged API catalog. Existing `pydelling.preview` imports remain supported for the 1.2 series.
- Add surface DFN upscaling and strengthen interpolation, raster writing, and optional integration tests.
- Split COMSOL, cloud visualization, HPC, and web application dependencies into extras; move development and documentation tools into dependency groups.
- Make `pyproject.toml` the single package version source; remove obsolete setuptools metadata.
- Build and test locked core/cloud environments and validate distribution contents before documentation deployment.

Use `uv sync --locked --extra cloud` for Cloud/VTK workflows. Use `--extra comsol`, `--extra hpc`, or `--extra webapps` for those integrations. Documentation tools use `--group docs`.

Pydelling Cloud pins the library commit through its submodule and records version 1.2.0 in its workspace lock. Update and commit both together; do not update the submodule to a floating branch during deployment.

## Version 1.0.5

*Release Date: 2024-09-24*

### 🎉 New Features

#### ComsolManager
- **New Class**: [ComsolManager](https://gitlab.amphos21.com/aitirga/pydelling/-/blob/main/pydelling/managers/comsol_manager.py?ref_type=heads)
  - Enables batch execution of multiple COMSOL files
  - Supports parametric sweeps of single .mph files
  - Integrated with HPC environments
  - Automatic result collection and analysis

#### ComsolPostprocessor  
- **New Class**: [ComsolPostprocessor](https://gitlab.amphos21.com/aitirga/pydelling/-/blob/main/pydelling/postprocessing/comsol_postprocessor.py?ref_type=heads)
  - Automated postprocessing of COMSOL simulation results
  - Data extraction and visualization tools
  - Report generation capabilities
  - Integration with pydelling analysis workflows

### 🔧 Improvements

- Enhanced documentation with comprehensive examples
- Improved error handling across all modules
- Better integration between COMSOL and PFLOTRAN workflows
- Performance optimizations in mesh processing routines

### 🐛 Bug Fixes

- Fixed memory leaks in large mesh processing
- Resolved coordinate system transformation issues
- Corrected unit conversion handling in various readers

### 📚 Documentation

- Completely revamped mkdocs documentation structure
- Added comprehensive API reference
- New tutorials and example workflows
- Improved installation and getting started guides

---

## Version 1.0.4

*Release Date: 2024-08-15*

### 🔄 Updates

#### ClosedStlGenerator
- **Fix**: [ClosedStlGenerator](https://gitlab.amphos21.com/aitirga/pydelling/-/blob/main/pydelling/preprocessing/closed_stl_generator.py?ref_type=heads)
  - Class was deprecated and has been updated and restored
  - Improved surface closure algorithms
  - Better handling of complex geometries
  - Enhanced manifold repair capabilities

### 🛠️ Technical Improvements

- Updated STL processing algorithms
- Improved geometric validation routines
- Better error messages for surface processing failures

---

## Version 1.0.3

*Release Date: 2024-07-20*

### 🐛 Critical Bug Fixes

#### PflotranManager
- **Fix**: [PflotranManager](https://gitlab.amphos21.com/aitirga/pydelling/-/tree/main/pydelling/managers?ref_type=heads)
  - **Issue**: Callbacks had a critical bug due to conflicts when passing variables
  - **Problem**: The `on_remote` variable was always set to `True` regardless of actual execution context
  - **Solution**: Fixed variable scoping and callback parameter handling
  - **Impact**: Remote vs. local execution now works correctly

### 🔧 Improvements

- Enhanced callback system robustness
- Better parameter validation in manager classes
- Improved error reporting for remote execution issues

---

## Version 1.0.2

*Release Date: 2024-06-25*

### ✨ New Features

#### iGPReader Enhancement
- **New Method**: [iGPReader.assign_material_from_stl()](https://gitlab.amphos21.com/aitirga/pydelling/-/blob/main/pydelling/readers/iGPReader/io/igp_reader.py#L932)
  - Assign material properties based on STL file geometry
  - Support for complex 3D material boundaries
  - Automatic inside/outside detection algorithms
  - Integration with mesh preprocessing workflows

### 🔧 Technical Details

- Enhanced geometric queries for material assignment
- Improved STL boundary detection algorithms
- Better handling of complex material interfaces
- Comprehensive validation of material assignments

### 📈 Performance

- Optimized spatial queries for large meshes
- Reduced memory usage in material assignment operations
- Faster STL boundary processing

---

## Version 1.0.1

*Release Date: 2024-05-30*

### 🔧 Major Fixes

#### PflotranManager Improvements
- **Enhancement**: [PflotranManager](https://gitlab.amphos21.com/aitirga/pydelling/-/tree/main/pydelling/managers?ref_type=heads)
  
##### New Features:
- **`-pflotran_dir` Parameter**: Added to improve flexibility when running locally
  - Allows custom PFLOTRAN installation paths
  - Better support for multiple PFLOTRAN versions
  - Simplified local development workflows

##### Bug Fixes:
- **SSH Reconnection**: Added automatic reconnection capability
  - Prevents disconnection issues during long-running simulations
  - Automatic retry mechanism for network interruptions
  - Better handling of HPC queue waiting times
  - Improved session persistence

### 🛠️ Technical Improvements

- Enhanced connection stability for remote execution
- Better error handling and recovery mechanisms
- Improved logging for troubleshooting connection issues
- More robust handling of HPC environment variations

### 🔒 Reliability

- Automatic session restoration after network interruptions
- Better detection and handling of connection timeouts
- Improved cleanup of failed remote sessions

---

## Version 1.0.0

*Release Date: 2024-04-15*

### 🚀 Initial Release

The first stable release of pydelling, featuring:

#### Core Modules

##### Readers
- **VTKReader**: Complete VTK format support
- **ConnectFlowReader**: ConnectFlow simulation output processing
- **PflotranObservationPointReader**: PFLOTRAN time series data
- **OpenFoamReader**: OpenFOAM case and field reading
- **FEMReader**: Generic finite element mesh support

##### Writers  
- **PflotranHdf5CentroidWriter**: Unstructured mesh data for PFLOTRAN
- **PflotranHdf5RasterWriter**: Structured grid data for PFLOTRAN
- **VTKWriter**: Standard visualization output
- **OpenFoamVariableWriter**: OpenFOAM field file generation

##### Preprocessing
- **MeshPreprocessor**: Comprehensive mesh cleaning and preparation
- **DfnPreprocessor**: Discrete fracture network processing
- **DfnUpscaler**: Scale-dependent property calculation
- **BoundaryProcessor**: Boundary condition assignment

##### Managers
- **PflotranManager**: PFLOTRAN simulation orchestration
- **Parameter study capabilities**: Automated parameter variations
- **Remote execution support**: HPC integration

##### Utilities
- **Geometry operations**: Spatial calculations and transformations  
- **File format conversions**: Multi-format data exchange
- **Validation tools**: Data integrity checking

#### Key Features

- **Multi-format Support**: VTK, HDF5, ConnectFlow, OpenFOAM, PFLOTRAN
- **HPC Integration**: Remote job submission and monitoring
- **Parameter Studies**: Automated sensitivity analysis
- **Comprehensive Testing**: Full test suite with CI/CD
- **Documentation**: Complete API reference and tutorials

#### Performance
- **Memory Efficient**: Chunked processing for large datasets
- **Parallel Processing**: Multi-core support where applicable
- **Scalable**: Designed for both desktop and HPC environments

---

## Development Roadmap

### Upcoming Features (Version 1.1.0)

#### Enhanced Simulation Management
- **Multi-physics Coupling**: Advanced coupling between different solvers
- **Uncertainty Quantification**: Built-in Monte Carlo and sensitivity analysis
- **Machine Learning Integration**: Data-driven model calibration
- **Real-time Monitoring**: Live simulation progress tracking

#### New Format Support
- **TOUGH2/TOUGH3**: Geothermal simulation support
- **MODFLOW**: Groundwater modeling integration  
- **ECLIPSE**: Reservoir simulation compatibility
- **Additional CAD Formats**: Extended geometry processing

#### Performance Enhancements
- **GPU Acceleration**: CUDA support for intensive operations
- **Distributed Computing**: MPI-based parallel processing
- **Database Integration**: Direct database connectivity
- **Cloud Computing**: AWS/Azure integration

#### User Experience
- **GUI Development**: Desktop application interface
- **Jupyter Integration**: Enhanced notebook support
- **Interactive Visualization**: Real-time data exploration
- **Web Dashboard**: Browser-based monitoring and control

### Long-term Vision (Version 2.0.0)

- **Complete Workflow Automation**: End-to-end simulation pipelines
- **AI-Assisted Modeling**: Intelligent parameter suggestion and optimization
- **Cross-platform Integration**: Seamless multi-solver workflows
- **Enterprise Features**: Advanced user management and deployment tools

---

## Contributing to Releases

### How to Contribute

1. **Feature Requests**: Submit issues with detailed requirements
2. **Bug Reports**: Provide reproducible test cases  
3. **Code Contributions**: Follow the [contributing guidelines](contributing.md)
4. **Documentation**: Help improve examples and tutorials
5. **Testing**: Add test cases and report compatibility issues

### Release Process

1. **Feature Development**: Implement and test new features
2. **Code Review**: Peer review and quality assurance
3. **Integration Testing**: Comprehensive testing across platforms
4. **Documentation Update**: Maintain up-to-date documentation
5. **Release Candidate**: Pre-release testing with community
6. **Stable Release**: Official version release with full support

---

## Version History Summary

| Version | Release Date | Key Features | Status |
|---------|--------------|--------------|---------|
| **1.0.5** | 2024-09-24 | COMSOL integration, enhanced docs | Current |
| **1.0.4** | 2024-08-15 | STL processing fixes | Supported |
| **1.0.3** | 2024-07-20 | PflotranManager callback fixes | Supported |
| **1.0.2** | 2024-06-25 | iGPReader STL material assignment | Supported |
| **1.0.1** | 2024-05-30 | PflotranManager improvements | Supported |
| **1.0.0** | 2024-04-15 | Initial stable release | Legacy |

---

*Stay updated with the latest pydelling developments by watching the [GitLab repository](https://gitlab.amphos21.com/aitirga/pydelling) and subscribing to release notifications.*