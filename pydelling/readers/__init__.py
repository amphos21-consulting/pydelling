"""Public reader namespace with backwards-compatible lazy exports."""

from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType
from typing import Any


_LAZY_EXPORTS = {
    "BaseReader": ("pydelling.readers.base_reader", "BaseReader"),
    "CentroidReader": ("pydelling.readers.centroid_reader", "CentroidReader"),
    "ConnectFlowMeshReader": (
        "pydelling.readers.connect_flow_mesh_reader",
        "ConnectFlowMeshReader",
    ),
    "ConnectFlowReader": ("pydelling.readers.connect_flow_reader", "ConnectFlowReader"),
    "FeflowReader": ("pydelling.readers.feflow_reader", "FeflowReader"),
    "FemReader": ("pydelling.readers.fem_reader", "FemReader"),
    "OpenFoamReader": ("pydelling.readers.open_foam_reader", "OpenFoamReader"),
    "PflotranMassBalanceFileReader": (
        "pydelling.readers.pflotran_mass_balance_file_reader",
        "PflotranMassBalanceFileReader",
    ),
    "PflotranObservationPointReader": (
        "pydelling.readers.pflotran_observation_point_reader",
        "PflotranObservationPointReader",
    ),
    "PflotranProcessingUtils": (
        "pydelling.readers.pflotran_processing_utils",
        "PflotranProcessingUtils",
    ),
    "PflotranReader": ("pydelling.readers.pflotran_reader", "PflotranReader"),
    "PflotranResults": ("pydelling.readers.pflotran_reader", "PflotranResults"),
    "RasterFileReader": ("pydelling.readers.raster_file_reader", "RasterFileReader"),
    "SmeshReader": ("pydelling.readers.smesh_reader", "SmeshReader"),
    "StreamlineReader": ("pydelling.readers.streamline_reader", "StreamlineReader"),
    "StructuredGridReader": (
        "pydelling.readers.structured_grid_reader",
        "StructuredGridReader",
    ),
    "StructuredListReader": (
        "pydelling.readers.structured_list_reader",
        "StructuredListReader",
    ),
    "TiffReader": ("pydelling.readers.tiff_reader", "TiffReader"),
    "UnstructuredMeshReader": (
        "pydelling.readers.unstructured_mesh_reader",
        "UnstructuredMeshReader",
    ),
    "VTKMeshReader": ("pydelling.readers.vtk_mesh_reader", "VTKMeshReader"),
    "VtkReader": ("pydelling.readers.vtk_reader", "VtkReader"),
    "iGPReader": ("pydelling.readers.iGPReader", "iGPReader"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_EXPORTS})


class _LazyReaderModule(ModuleType):
    """Keep class exports stable when a same-named submodule is imported."""

    def __getattribute__(self, name: str) -> Any:
        namespace = ModuleType.__getattribute__(self, "__dict__")
        exports = namespace.get("_LAZY_EXPORTS", {})
        current = namespace.get(name)
        if name in exports and isinstance(current, ModuleType):
            module_name, attribute = exports[name]
            value = getattr(import_module(module_name), attribute)
            namespace[name] = value
            return value
        return ModuleType.__getattribute__(self, name)


sys.modules[__name__].__class__ = _LazyReaderModule


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
    *_LAZY_EXPORTS,
]
