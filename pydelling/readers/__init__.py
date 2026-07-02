"""Reader package namespace.

Upstream eagerly imports every reader, but the cloud app only needs a few
explicit reader modules. Keep package import side effects minimal so
``pydelling.readers.vtk_mesh_reader`` can be used without bootstrapping the full
legacy configuration stack.
"""

from pydelling.readers.centroid_reader import CentroidReader
from pydelling.readers.iGPReader import iGPReader

__all__ = [
    "base_reader",
    "centroid_reader",
    "CentroidReader",
    "connect_flow_mesh_reader",
    "connect_flow_reader",
    "fem_reader",
    "open_foam_reader",
    "pflotran_mass_balance_file_reader",
    "pflotran_observation_point_reader",
    "pflotran_processing_utils",
    "pflotran_reader",
    "raster_file_reader",
    "smesh_reader",
    "streamline_reader",
    "structured_grid_reader",
    "structured_list_reader",
    "tiff_reader",
    "unstructured_mesh_reader",
    "vtk_mesh_reader",
    "vtk_reader",
    "iGPReader",
]
