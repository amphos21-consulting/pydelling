"""Read PFLOTRAN unstructured-explicit region and material files.

Symmetric counterpart to :class:`PflotranExplicitWriter`:

* ``.mat`` material files are one integer cell id per line
  (``write_materials``).
* ``.ex`` condition files start with a ``CONNECTIONS N`` header followed by
  ``element_id x y z area`` rows (``write_condition_data``).

These are PFLOTRAN-specific formats produced by the iGP explicit export, so the
logic to read them back lives here next to the writer that emits them.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np

from pydelling.preprocessing.mesh_preprocessor.array_mesh import (
    ArrayMesh,
    assign_material_regions,
    read_pflotran_explicit_mesh,
)


def _loadtxt(path: Path, **kwargs) -> np.ndarray:
    """``np.loadtxt`` without the noisy "input contained no data" warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        return np.loadtxt(path, **kwargs)


class PflotranExplicitReader:
    """Read PFLOTRAN explicit ``.mat`` / ``.ex`` files into summary dictionaries."""

    @staticmethod
    def read_mesh(
        path: str | Path,
        *,
        bounds: tuple[float, float, float, float, float, float] | None = None,
        cell_ids=None,
    ) -> ArrayMesh:
        """Read a combined CELLS/ELEMENTS/VERTICES mesh without element objects."""

        return read_pflotran_explicit_mesh(path, bounds=bounds, cell_ids=cell_ids)

    @staticmethod
    def assign_material_regions(
        mesh: ArrayMesh,
        regions: dict[int, str | Path],
        *,
        require_complete: bool = True,
    ) -> np.ndarray:
        """Assign one material ID to each mesh cell from PFLOTRAN ``.mat`` files."""

        return assign_material_regions(mesh, regions, require_complete=require_complete)

    @staticmethod
    def read_material_ids(path: str | Path) -> dict:
        """Summarize a PFLOTRAN ``.mat`` material file (one cell id per line).

        Category: reader
        Tags: pflotran, materials, explicit-mesh, cell-ids
        Usage: scripts need the cell-id membership of a PFLOTRAN material region.

        Returns:
            dict: ``count``, ``min``, ``max`` and the ``ids`` array (int64).
        """
        path = Path(path)
        ids = _loadtxt(path, dtype=np.int64, ndmin=1)
        if ids.size == 0:
            return {"count": 0, "min": None, "max": None, "ids": ids}
        return {
            "count": int(ids.size),
            "min": int(ids.min()),
            "max": int(ids.max()),
            "ids": ids,
        }

    @staticmethod
    def read_boundary_connections(path: str | Path) -> dict:
        """Summarize a PFLOTRAN ``.ex`` explicit boundary condition file.

        Category: reader
        Tags: pflotran, boundary-condition, explicit-mesh, connections, area
        Usage: scripts need the face count and areas of a PFLOTRAN boundary region.

        Returns:
            dict: ``declared_count`` (header), ``face_count`` (rows),
            ``total_area``, ``area_min``, ``area_max``, ``bbox`` and the raw
            ``element_ids``/``areas`` arrays.
        """
        path = Path(path)
        declared_count: int | None = None
        with path.open("r") as handle:
            first_line = handle.readline().split()
        if first_line and first_line[0].upper() == "CONNECTIONS" and len(first_line) > 1:
            try:
                declared_count = int(first_line[1])
            except ValueError:
                declared_count = None
        skiprows = 1 if declared_count is not None else 0

        data = _loadtxt(path, skiprows=skiprows, ndmin=2)
        if data.size == 0:
            return {
                "declared_count": declared_count,
                "face_count": 0,
                "total_area": 0.0,
                "area_min": None,
                "area_max": None,
                "bbox": None,
                "element_ids": np.empty(0, dtype=np.int64),
                "centroids": np.empty((0, 3), dtype=np.float64),
                "areas": np.empty(0, dtype=np.float64),
            }

        # Columns: element_id, x, y, z, area
        element_ids = data[:, 0].astype(np.int64)
        coords = data[:, 1:4]
        areas = data[:, 4]
        return {
            "declared_count": declared_count,
            "face_count": int(data.shape[0]),
            "total_area": float(areas.sum()),
            "area_min": float(areas.min()),
            "area_max": float(areas.max()),
            "bbox": {
                "min": coords.min(axis=0).tolist(),
                "max": coords.max(axis=0).tolist(),
            },
            "element_ids": element_ids,
            "centroids": coords,
            "areas": areas,
        }


def read_material_ids(path: str | Path) -> dict:
    """Module-level convenience wrapper for :meth:`PflotranExplicitReader.read_material_ids`."""
    return PflotranExplicitReader.read_material_ids(path)


def read_boundary_connections(path: str | Path) -> dict:
    """Module-level convenience wrapper for :meth:`PflotranExplicitReader.read_boundary_connections`."""
    return PflotranExplicitReader.read_boundary_connections(path)
