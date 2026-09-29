"""Post-processing callbacks run where each study ran; see :mod:`.base`.

- :class:`ObservationPoints`: PFLOTRAN observation files (``OBSERVATION`` cards).
- :class:`ExtractHDF5`: cells (:class:`Cell`, :class:`Cells`) and regions (:class:`Region`,
  :class:`Domain`) of the HDF5 snapshots, as time series.
- :class:`FunctionCallback` or a :class:`PostprocessCallback` subclass: anything else.
"""

from .base import (
    FunctionCallback,
    PostprocessCallback,
    processed_intact,
    run_postprocess,
    validate_postprocess,
    write_table,
)
from .geometry import CellGeometry
from .hdf5 import ExtractHDF5
from .observations import ObservationPoints
from .selections import AGGREGATES, Cell, Cells, Domain, Region, Selection

__all__ = [
    "AGGREGATES",
    "Cell",
    "CellGeometry",
    "Cells",
    "Domain",
    "ExtractHDF5",
    "FunctionCallback",
    "ObservationPoints",
    "PostprocessCallback",
    "Region",
    "Selection",
    "processed_intact",
    "run_postprocess",
    "validate_postprocess",
    "write_table",
]
