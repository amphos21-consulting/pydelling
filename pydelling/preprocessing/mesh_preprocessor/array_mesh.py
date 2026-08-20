"""Compact, array-backed convex-cell meshes used by DFN upscaling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import mmap

import meshio
import numpy as np


CELL_NODE_COUNTS = {"T": 4, "P": 5, "W": 6, "H": 8}
CELL_MESHIO_TYPES = {"T": "tetra", "P": "pyramid", "W": "wedge", "H": "hexahedron"}

# Local face order follows the element order written by iGP/PFLOTRAN.
CELL_FACES = {
    "T": ((0, 1, 3), (1, 2, 3), (0, 3, 2), (0, 2, 1)),
    "P": ((0, 1, 2, 3), (0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0)),
    "W": ((0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5), (0, 2, 1), (3, 4, 5)),
    "H": (
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
        (0, 3, 2, 1),
        (4, 5, 6, 7),
    ),
}


class PflotranMeshError(ValueError):
    """Raised when a PFLOTRAN text mesh is malformed or unsupported."""


@dataclass
class ArrayMesh:
    """A compact convex-cell mesh with stable source IDs.

    Connectivity indexes ``points`` locally. ``cell_ids`` and ``point_ids``
    preserve the one-based IDs from the source file.
    """

    points: np.ndarray
    connectivity: np.ndarray
    cell_types: np.ndarray
    cell_ids: np.ndarray
    centroids: np.ndarray
    volumes: np.ndarray
    point_ids: np.ndarray | None = None
    material_ids: np.ndarray | None = None
    cell_data: dict[str, np.ndarray] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.points = np.asarray(self.points, dtype=np.float64)
        self.connectivity = np.asarray(self.connectivity, dtype=np.int64)
        self.cell_types = np.asarray(self.cell_types, dtype="U1")
        self.cell_ids = np.asarray(self.cell_ids, dtype=np.int64)
        self.centroids = np.asarray(self.centroids, dtype=np.float64)
        self.volumes = np.asarray(self.volumes, dtype=np.float64)
        if self.point_ids is None:
            self.point_ids = np.arange(1, len(self.points) + 1, dtype=np.int64)
        else:
            self.point_ids = np.asarray(self.point_ids, dtype=np.int64)
        n_cells = len(self.cell_ids)
        if self.centroids.shape != (n_cells, 3) or self.volumes.shape != (n_cells,):
            raise PflotranMeshError("centroids/volumes do not match the cell count")
        if self.connectivity.shape != (n_cells, 8):
            raise PflotranMeshError("connectivity must have shape (n_cells, 8)")
        if np.any(self.volumes <= 0):
            raise PflotranMeshError("cell volumes must be positive")
        if self.material_ids is not None:
            self.material_ids = np.asarray(self.material_ids, dtype=np.int32)
            if self.material_ids.shape != (n_cells,):
                raise PflotranMeshError("material_ids does not match the cell count")

    @property
    def n_cells(self) -> int:
        return len(self.cell_ids)

    @property
    def n_points(self) -> int:
        return len(self.points)

    @property
    def cell_bounds(self) -> np.ndarray:
        cached = getattr(self, "_cell_bounds", None)
        if cached is None:
            bounds = np.empty((self.n_cells, 6), dtype=np.float64)
            for code, count in CELL_NODE_COUNTS.items():
                ids = np.flatnonzero(self.cell_types == code)
                if not len(ids):
                    continue
                coords = self.points[self.connectivity[ids, :count]]
                bounds[ids, :3] = coords.min(axis=1)
                bounds[ids, 3:] = coords.max(axis=1)
            self._cell_bounds = bounds
            cached = bounds
        return cached

    def cell_vertices(self, index: int) -> np.ndarray:
        count = CELL_NODE_COUNTS[str(self.cell_types[index])]
        return self.points[self.connectivity[index, :count]]

    def subset(
        self,
        *,
        bounds: tuple[float, float, float, float, float, float] | None = None,
        cell_ids: Iterable[int] | None = None,
    ) -> "ArrayMesh":
        mask = np.ones(self.n_cells, dtype=bool)
        if bounds is not None:
            xmin, xmax, ymin, ymax, zmin, zmax = map(float, bounds)
            mask &= (
                (self.centroids[:, 0] >= xmin)
                & (self.centroids[:, 0] <= xmax)
                & (self.centroids[:, 1] >= ymin)
                & (self.centroids[:, 1] <= ymax)
                & (self.centroids[:, 2] >= zmin)
                & (self.centroids[:, 2] <= zmax)
            )
        if cell_ids is not None:
            mask &= np.isin(self.cell_ids, np.fromiter(cell_ids, dtype=np.int64))
        selected = np.flatnonzero(mask)
        if not len(selected):
            raise PflotranMeshError("mesh subset contains no cells")

        old_conn = self.connectivity[selected]
        used = np.unique(old_conn[old_conn >= 0])
        remap = np.full(self.n_points, -1, dtype=np.int64)
        remap[used] = np.arange(len(used), dtype=np.int64)
        conn = old_conn.copy()
        valid = conn >= 0
        conn[valid] = remap[conn[valid]]
        return ArrayMesh(
            points=self.points[used],
            connectivity=conn,
            cell_types=self.cell_types[selected],
            cell_ids=self.cell_ids[selected],
            centroids=self.centroids[selected],
            volumes=self.volumes[selected],
            point_ids=self.point_ids[used],
            material_ids=None if self.material_ids is None else self.material_ids[selected],
            cell_data={name: np.asarray(data)[selected] for name, data in self.cell_data.items()},
            metadata=dict(self.metadata),
        )

    def to_meshio(self, extra_cell_data: dict[str, np.ndarray] | None = None) -> meshio.Mesh:
        blocks: list[tuple[str, np.ndarray]] = []
        block_indices: list[np.ndarray] = []
        for code in ("T", "P", "W", "H"):
            indices = np.flatnonzero(self.cell_types == code)
            if len(indices):
                blocks.append(
                    (CELL_MESHIO_TYPES[code], self.connectivity[indices, : CELL_NODE_COUNTS[code]])
                )
                block_indices.append(indices)
        arrays = dict(self.cell_data)
        if self.material_ids is not None:
            arrays.setdefault("material_id", self.material_ids)
        if extra_cell_data:
            arrays.update(extra_cell_data)
        cell_data: dict[str, list[np.ndarray]] = {}
        for name, values in arrays.items():
            values = np.asarray(values)
            if len(values) != self.n_cells:
                raise PflotranMeshError(f"cell array {name!r} has the wrong length")
            cell_data[name] = [values[indices] for indices in block_indices]
        return meshio.Mesh(points=self.points, cells=blocks, cell_data=cell_data)

    def write_vtk(self, filename: str | Path, cell_data: dict[str, np.ndarray] | None = None) -> Path:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_meshio(cell_data).write(path)
        return path


def _find_section(mapped: mmap.mmap, name: bytes) -> int:
    marker = b"\n" + name + b" "
    # mmap.find() otherwise starts at the current seek position.  The parser
    # deliberately jumps between sections, so always search from the start.
    offset = mapped.find(marker, 0)
    if offset < 0:
        if mapped[: len(name) + 1] == name + b" ":
            return 0
        raise PflotranMeshError(f"{name.decode()} section not found")
    return offset + 1


def read_pflotran_explicit_mesh(
    path: str | Path,
    *,
    bounds: tuple[float, float, float, float, float, float] | None = None,
    cell_ids: Iterable[int] | None = None,
) -> ArrayMesh:
    """Read the combined PFLOTRAN CELLS/ELEMENTS/VERTICES text format."""

    path = Path(path).expanduser().resolve()
    with path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
        cells_offset = _find_section(mapped, b"CELLS")
        mapped.seek(cells_offset)
        header = mapped.readline().split()
        if len(header) != 2:
            raise PflotranMeshError("invalid CELLS header")
        n_cells = int(header[1])
        source_cell_ids = np.empty(n_cells, dtype=np.int64)
        centroids = np.empty((n_cells, 3), dtype=np.float64)
        volumes = np.empty(n_cells, dtype=np.float64)
        for index in range(n_cells):
            fields = mapped.readline().split()
            if len(fields) != 5:
                raise PflotranMeshError(f"invalid CELLS row {index + 1}")
            source_cell_ids[index] = int(fields[0])
            centroids[index] = tuple(map(float, fields[1:4]))
            volumes[index] = float(fields[4])

        elements_offset = _find_section(mapped, b"ELEMENTS")
        mapped.seek(elements_offset)
        header = mapped.readline().split()
        n_elements = int(header[1])
        if n_elements != n_cells:
            raise PflotranMeshError("CELLS and ELEMENTS counts differ")
        connectivity = np.full((n_cells, 8), -1, dtype=np.int64)
        cell_types = np.empty(n_cells, dtype="U1")
        for index in range(n_cells):
            fields = mapped.readline().split()
            if not fields:
                raise PflotranMeshError(f"missing ELEMENTS row {index + 1}")
            code = fields[0].decode("ascii").upper()
            if code not in CELL_NODE_COUNTS:
                raise PflotranMeshError(f"unsupported element type {code!r}")
            count = CELL_NODE_COUNTS[code]
            if len(fields) != count + 1:
                raise PflotranMeshError(f"invalid {code} connectivity at row {index + 1}")
            cell_types[index] = code
            connectivity[index, :count] = np.asarray(fields[1:], dtype=np.int64) - 1

        vertices_offset = _find_section(mapped, b"VERTICES")
        mapped.seek(vertices_offset)
        header = mapped.readline().split()
        n_points = int(header[1])
        points = np.empty((n_points, 3), dtype=np.float64)
        for index in range(n_points):
            fields = mapped.readline().split()
            if len(fields) != 3:
                raise PflotranMeshError(f"invalid VERTICES row {index + 1}")
            points[index] = tuple(map(float, fields))

    if np.any(connectivity >= n_points):
        raise PflotranMeshError("element references a missing vertex")
    mesh = ArrayMesh(
        points=points,
        connectivity=connectivity,
        cell_types=cell_types,
        cell_ids=source_cell_ids,
        centroids=centroids,
        volumes=volumes,
        metadata={"source": str(path)},
    )
    if bounds is not None or cell_ids is not None:
        mesh = mesh.subset(bounds=bounds, cell_ids=cell_ids)
    return mesh


def assign_material_regions(
    mesh: ArrayMesh,
    regions: dict[int, str | Path | Iterable[int]],
    *,
    require_complete: bool = True,
) -> np.ndarray:
    """Assign exactly one material to every selected source cell ID."""

    assignments = np.zeros(mesh.n_cells, dtype=np.int32)
    id_to_local = {int(source_id): i for i, source_id in enumerate(mesh.cell_ids)}
    for material_id, source in regions.items():
        if isinstance(source, (str, Path)):
            values = np.loadtxt(source, dtype=np.int64, ndmin=1)
        else:
            values = np.fromiter(source, dtype=np.int64)
        for source_id in values:
            local = id_to_local.get(int(source_id))
            if local is None:
                continue
            if assignments[local] != 0:
                raise PflotranMeshError(
                    f"cell {source_id} occurs in materials {assignments[local]} and {material_id}"
                )
            assignments[local] = int(material_id)
    if require_complete and np.any(assignments == 0):
        missing = mesh.cell_ids[assignments == 0]
        raise PflotranMeshError(f"{len(missing)} cells have no material assignment")
    mesh.material_ids = assignments
    return assignments
