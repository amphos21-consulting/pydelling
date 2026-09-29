"""Cell geometry of a PFLOTRAN grid: centers, volumes and extents in natural (id) order.

Natural ids are 1-based and, for structured grids, run along x first, then y, then z.
Geometry comes from, in order of preference:

- structured grids: the HDF5 ``Coordinates`` group (cell edges), or the deck's ``GRID``
  (``NXYZ`` with ``BOUNDS`` or ``DXYZ``, optional ``ORIGIN``);
- explicit unstructured grids: the ``CELLS`` table of the deck's ``.uge`` file;
- implicit unstructured grids: the HDF5 ``Domain/Cells`` and ``Domain/Vertices`` datasets
  (centers are vertex means, volumes come from a tetrahedral decomposition).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import h5py
import numpy as np

from .observations import fortran_float

if TYPE_CHECKING:
    from pydelling.managers.pflotran_study import PflotranStudy

# XDMF mixed-topology cell codes written by PFLOTRAN: code -> vertex count
XDMF_CELLS = {6: 4, 7: 5, 8: 6, 9: 8}
# Tetrahedra (local vertex indices) that split each cell shape, keyed by vertex count.
TETRAHEDRA = {
    4: [(0, 1, 2, 3)],
    5: [(0, 1, 2, 4), (0, 2, 3, 4)],
    6: [(0, 1, 2, 3), (1, 2, 3, 4), (2, 3, 4, 5)],
    8: [(0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6)],
}


def deck_numbers(tokens: Sequence[str]) -> list[float]:
    """Numbers of deck tokens, expanding ``n*value`` repeats (``200*0.05``)."""
    values = []
    for token in tokens:
        count, star, value = str(token).partition("*")
        if star:
            values += [fortran_float(value)] * int(count)
        else:
            values.append(fortran_float(token))
    return values


def locate_file(study: PflotranStudy, token: str, workdir: Path | None) -> Path:
    """Find a file referenced by the deck.

    Args:
        study: The study whose deck references the file.
        token: Path as written in the deck (``input_files/mesh.uge``).
        workdir: Folder where the study ran, if it did.

    Returns:
        Path: The file in ``workdir``, else the study's registered input file with that name,
        else the file next to the template.

    Raises:
        FileNotFoundError: If none exists.
    """
    candidates = []
    if workdir is not None:
        candidates.append(Path(workdir) / token)
    name = Path(token).name
    if name in study.aux_files:
        candidates.append(Path(study.aux_files[name]))
    candidates.append(Path(study.input_file).parent / token)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"File {token!r} referenced by the deck was not found")


@dataclass
class CellGeometry:
    """Cells of a grid in natural order (row ``n - 1`` is cell id ``n``).

    Attributes:
        centers: ``(n, 3)`` cell centers.
        volumes: ``(n,)`` cell volumes, if known.
        lower: ``(n, 3)`` lower corners of structured cells, else None.
        upper: ``(n, 3)`` upper corners of structured cells, else None.
        shape: ``(nx, ny, nz)`` of a structured grid, else None.
        domain: ``(lower, upper)`` corners of the domain, if known beyond the centers.
    """

    centers: np.ndarray
    volumes: np.ndarray | None = None
    lower: np.ndarray | None = None
    upper: np.ndarray | None = None
    shape: tuple[int, int, int] | None = None
    domain: tuple[np.ndarray, np.ndarray] | None = None

    @property
    def size(self) -> int:
        """Number of cells."""
        return len(self.centers)

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """Lower and upper corners of the domain."""
        if self.domain is not None:
            return self.domain
        if self.lower is not None:
            return self.lower.min(axis=0), self.upper.max(axis=0)
        return self.centers.min(axis=0), self.centers.max(axis=0)

    @classmethod
    def structured(
        cls, x: Sequence[float], y: Sequence[float], z: Sequence[float]
    ) -> CellGeometry:
        """Structured grid from its cell edges along each axis.

        Args:
            x: ``nx + 1`` increasing edges; likewise ``y`` and ``z``.

        Returns:
            CellGeometry: Cells in natural order.
        """
        edges = [np.asarray(axis, dtype=float) for axis in (x, y, z)]
        if any(len(axis) < 2 or np.any(np.diff(axis) <= 0) for axis in edges):
            raise ValueError("Structured grid edges must be increasing, two or more per axis")
        grids = [np.meshgrid(*(a[:-1] for a in edges), indexing="ij"),
                 np.meshgrid(*(a[1:] for a in edges), indexing="ij")]
        lower = np.stack([g.reshape(-1, order="F") for g in grids[0]], axis=1)
        upper = np.stack([g.reshape(-1, order="F") for g in grids[1]], axis=1)
        shape = tuple(len(axis) - 1 for axis in edges)
        return cls(
            centers=(lower + upper) / 2,
            volumes=np.prod(upper - lower, axis=1),
            lower=lower,
            upper=upper,
            shape=shape,
        )

    @classmethod
    def implicit(cls, cells: np.ndarray, vertices: np.ndarray) -> CellGeometry:
        """Implicit unstructured grid from PFLOTRAN's ``Domain`` datasets.

        Args:
            cells: XDMF mixed topology (``[code, v0, v1, ...]`` per cell, codes 6 tet,
                7 pyramid, 8 wedge, 9 hexahedron) or an ``(n, 9)`` table
                ``[vertex count, v0, ..., v7]``; vertex indices are 0-based.
            vertices: ``(m, 3)`` vertex coordinates.

        Returns:
            CellGeometry: Centers and volumes of each cell.
        """
        vertices = np.asarray(vertices, dtype=float)
        cells = np.asarray(cells, dtype=int)
        connectivity = []
        if cells.ndim == 2:
            connectivity = [row[1:1 + row[0]] for row in cells]
        else:
            position = 0
            while position < len(cells):
                code = int(cells[position])
                if code not in XDMF_CELLS:
                    raise ValueError(f"Unsupported XDMF cell code {code} in Domain/Cells")
                count = XDMF_CELLS[code]
                connectivity.append(cells[position + 1:position + 1 + count])
                position += 1 + count
        centers, volumes = [], []
        for nodes in connectivity:
            points = vertices[nodes]
            if len(nodes) not in TETRAHEDRA:
                raise ValueError(f"Unsupported cell with {len(nodes)} vertices")
            centers.append(points.mean(axis=0))
            volumes.append(
                sum(
                    abs(np.linalg.det(points[list(tet[1:])] - points[tet[0]])) / 6
                    for tet in TETRAHEDRA[len(nodes)]
                )
            )
        return cls(
            centers=np.array(centers),
            volumes=np.array(volumes),
            domain=(vertices.min(axis=0), vertices.max(axis=0)),
        )

    @classmethod
    def from_uge(cls, path: str | Path) -> CellGeometry:
        """Explicit unstructured grid from the ``CELLS`` block of a ``.uge`` file.

        Args:
            path: File with ``CELLS n`` followed by ``id x y z volume`` rows.

        Returns:
            CellGeometry: Cells sorted by id (ids must be ``1..n``).
        """
        lines = Path(path).read_text().split("\n")
        header = next((i for i, line in enumerate(lines) if line.split()[:1] == ["CELLS"]), None)
        if header is None:
            raise ValueError(f"{Path(path).name}: no CELLS block")
        count = int(lines[header].split()[1])
        rows = np.array(
            [deck_numbers(line.split()[:5]) for line in lines[header + 1:header + 1 + count]]
        )
        order = np.argsort(rows[:, 0])
        rows = rows[order]
        if not np.array_equal(rows[:, 0], np.arange(1, count + 1)):
            raise ValueError(f"{Path(path).name}: cell ids must be 1..{count}")
        return cls(centers=rows[:, 1:4], volumes=rows[:, 4])

    @classmethod
    def from_hdf5(cls, path: str | Path) -> CellGeometry | None:
        """Geometry stored in a PFLOTRAN HDF5 output file, if any.

        Args:
            path: A snapshot file.

        Returns:
            CellGeometry | None: Structured (``Coordinates``) or implicit (``Domain``)
            geometry, or None (explicit grids store none).
        """
        with h5py.File(path, "r") as data:
            if "Coordinates" in data:
                group = data["Coordinates"]
                axes = {name[:1].upper(): group[name][...] for name in group}
                return cls.structured(axes["X"], axes["Y"], axes["Z"])
            if "Domain" in data and {"Cells", "Vertices"} <= set(data["Domain"]):
                return cls.implicit(data["Domain/Cells"][...], data["Domain/Vertices"][...])
        return None

    @classmethod
    def from_deck(cls, study: PflotranStudy, workdir: Path | None = None) -> CellGeometry | None:
        """Geometry described by the deck's ``GRID``, if it can be read without running.

        Args:
            study: A PFLOTRAN study.
            workdir: Folder where the study ran, to find a ``.uge`` file there.

        Returns:
            CellGeometry | None: Structured or explicit geometry; None for implicit grids,
            unset placeholders or grid cards this reader does not know.
        """
        try:
            grid_type = [token.upper() for token in study["GRID/TYPE"]]
            if grid_type[0] == "UNSTRUCTURED_EXPLICIT":
                return cls.from_uge(locate_file(study, study["GRID/TYPE"][1], workdir))
            if grid_type[0] != "STRUCTURED":
                return None
            shape = [int(value) for value in deck_numbers(study["GRID/NXYZ"])]
            if "GRID/BOUNDS" in study:
                low, high = (deck_numbers(row) for row in study["GRID/BOUNDS"])
                edges = [np.linspace(low[a], high[a], shape[a] + 1) for a in range(3)]
            else:
                origin = deck_numbers(study["GRID/ORIGIN"]) if "GRID/ORIGIN" in study else [0] * 3
                rows = study["GRID/DXYZ"]
                edges = []
                for axis, row in enumerate(rows):
                    widths = deck_numbers(row)
                    if len(widths) == 1:
                        widths *= shape[axis]
                    if len(widths) != shape[axis]:
                        raise ValueError("DXYZ does not match NXYZ")
                    edges.append(origin[axis] + np.concatenate([[0], np.cumsum(widths)]))
            return cls.structured(*edges)
        except (KeyError, ValueError, IndexError):  # placeholders, unknown syntax: check later
            return None

    def natural(self, values: np.ndarray) -> np.ndarray:
        """Snapshot values in natural order.

        Args:
            values: A dataset of a ``Time:`` group, ``(nx, ny, nz)`` for structured grids or
                ``(n,)`` otherwise.

        Returns:
            np.ndarray: ``(n,)`` values, row ``n - 1`` for cell id ``n``.
        """
        values = np.asarray(values)
        flat = values.reshape(-1, order="F") if values.ndim == 3 else values.reshape(-1)
        if len(flat) != self.size:
            raise ValueError(f"{len(flat)} values for a grid of {self.size} cells")
        return flat
