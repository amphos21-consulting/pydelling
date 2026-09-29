"""Which cells an HDF5 extraction reads, and how a group of cells becomes one value.

A selection returns 1-based natural cell ids (:meth:`Selection.cells`). ``Cell`` and
``Cells`` report each cell; ``Region`` and ``Domain`` reduce their cells with an aggregate
(``mean``, ``volume_mean``, ``sum``, ``integral``, ``min``, ``max`` or a function
``f(values, volumes) -> float``). Subclass :class:`Selection` for other rules.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import h5py
import numpy as np

from .base import import_object, object_path
from .geometry import CellGeometry, deck_numbers, locate_file

if TYPE_CHECKING:
    from pydelling.managers.pflotran_study import PflotranStudy

Aggregate = str | Callable[[np.ndarray, np.ndarray | None], float]


def _volume_weighted(values: np.ndarray, volumes: np.ndarray) -> float:
    return float(np.sum(values * volumes) / np.sum(volumes))


AGGREGATES: dict[str, tuple[Callable[..., float], bool]] = {
    # name: (function(values, volumes), needs volumes)
    "mean": (lambda values, volumes: float(np.mean(values)), False),
    "volume_mean": (_volume_weighted, True),
    "sum": (lambda values, volumes: float(np.sum(values)), False),
    "integral": (lambda values, volumes: float(np.sum(values * volumes)), True),
    "min": (lambda values, volumes: float(np.min(values)), False),
    "max": (lambda values, volumes: float(np.max(values)), False),
}


def check_aggregate(how: Aggregate | None) -> Aggregate | None:
    """Return ``how`` resolved (``"module:function"`` strings are imported); raise if unknown."""
    if how is None or callable(how) or how in AGGREGATES:
        return how
    if isinstance(how, str) and ":" in how:
        return import_object(how)
    raise ValueError(f"Unknown aggregate {how!r}; use one of {sorted(AGGREGATES)} or a function")


def aggregate(how: Aggregate, values: np.ndarray, volumes: np.ndarray | None) -> float:
    """Reduce the values of several cells to one number.

    Args:
        how: Aggregate name or ``function(values, volumes) -> float``.
        values: Values of the selected cells.
        volumes: Their volumes, or None when the grid geometry is unknown.

    Returns:
        float: The aggregated value.

    Raises:
        ValueError: If the aggregate needs volumes and there are none.
    """
    if callable(how):
        return float(how(values, volumes))
    function, needs_volumes = AGGREGATES[how]
    if needs_volumes and volumes is None:
        raise ValueError(f"Aggregate {how!r} needs cell volumes; the grid geometry is unknown")
    return function(values, volumes)


def _aggregate_spec(how: Aggregate | None) -> str | None:
    return how if how is None or isinstance(how, str) else object_path(how)


def _need(geometry: CellGeometry | None, what: str) -> CellGeometry:
    if geometry is None:
        raise ValueError(f"{what} needs the grid geometry, which is unknown for this grid")
    return geometry


def _nearest(geometry: CellGeometry, point: Sequence[float | None]) -> int:
    axes = [axis for axis, value in enumerate(point) if value is not None]
    if not axes:
        raise ValueError("A point needs at least one coordinate")
    target = np.array([point[axis] for axis in axes], dtype=float)
    low, high = geometry.bounds
    span = np.maximum(high - low, 1.0)
    tolerance = 1e-9 * span[axes]
    if np.any(target < low[axes] - tolerance) or np.any(target > high[axes] + tolerance):
        raise ValueError(f"Point {list(point)} is outside the grid {low.tolist()}-{high.tolist()}")
    distance = np.sum((geometry.centers[:, axes] - target) ** 2, axis=1)
    return int(np.argmin(distance)) + 1


def _in_box(geometry: CellGeometry, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    """Ids of cells in a box: overlapping extents (structured) or centers inside (otherwise)."""
    low, high = np.minimum(low, high), np.maximum(low, high)
    if geometry.lower is not None:
        flat = high <= low
        # A zero-width axis (a face such as REGION west) keeps the cells touching it.
        touching = (geometry.lower <= high) & (geometry.upper >= low)
        overlapping = (geometry.lower < high) & (geometry.upper > low)
        inside = np.where(flat, touching, overlapping).all(axis=1)
    else:
        inside = ((geometry.centers >= low) & (geometry.centers <= high)).all(axis=1)
    return np.flatnonzero(inside) + 1


def _check_ids(ids: np.ndarray, geometry: CellGeometry | None) -> np.ndarray:
    ids = np.asarray(ids, dtype=int).reshape(-1)
    if np.any(ids < 1):
        raise ValueError(f"Cell ids are 1-based; got {ids[ids < 1].tolist()}")
    if geometry is not None and np.any(ids > geometry.size):
        bad = ids[ids > geometry.size][0]
        raise ValueError(f"id {bad} is not a cell of this grid (1..{geometry.size})")
    return ids


class Selection:
    """Base class: which cells to read, and how to reduce them.

    Args:
        aggregate: How several cells become one value; None reports each cell.

    Example:
        ```python
        class Wells(Selection):
            def cells(self, geometry, study, workdir):
                return np.array([12, 40, 77])

        ExtractHDF5("Liquid Pressure*", {"wells": Wells(aggregate="mean")})
        ```
    """

    #: One output row per cell instead of one aggregated row.
    per_cell = False

    def __init__(self, aggregate: Aggregate | None = None) -> None:
        self.aggregate = check_aggregate(aggregate)

    def cells(
        self, geometry: CellGeometry | None, study: PflotranStudy | None, workdir: Path | None
    ) -> np.ndarray:
        """1-based natural ids of the selected cells.

        Args:
            geometry: Grid geometry, or None when unknown.
            study: The study (its deck names regions).
            workdir: Folder where the study ran; None before running.

        Returns:
            np.ndarray: Cell ids.
        """
        raise NotImplementedError

    def needs_geometry(self, study: PflotranStudy | None) -> bool:
        """Whether :meth:`cells` needs the grid geometry (checks are deferred without it)."""
        return True

    def validate(self, geometry: CellGeometry | None, study: PflotranStudy) -> None:
        """Check the selection before running; without geometry only what the deck tells."""
        if geometry is None and self.needs_geometry(study):
            return
        self.cells(geometry, study, None)

    def options(self) -> dict:
        """Keyword arguments that rebuild this selection (JSON values)."""
        return {"aggregate": _aggregate_spec(self.aggregate)}

    def spec(self) -> dict:
        """``{"type": "module:Class", "options": {...}}``."""
        return {"type": object_path(type(self)), "options": self.options()}

    @staticmethod
    def from_spec(spec: dict) -> Selection:
        """Rebuild a selection from :meth:`spec`."""
        cls = import_object(spec["type"])
        if not (isinstance(cls, type) and issubclass(cls, Selection)):
            raise TypeError(f"{spec['type']} is not a Selection")
        return cls(**spec.get("options", {}))

    def __repr__(self) -> str:
        options = ", ".join(f"{k}={v!r}" for k, v in self.options().items() if v is not None)
        return f"{type(self).__name__}({options})"


class Cell(Selection):
    """One cell: nearest to a point, by natural id, or by structured index.

    Args:
        x: Point coordinates; axes left as None are ignored (``Cell(x=10.0)`` on a column).
        y: See ``x``.
        z: See ``x``.
        id: 1-based natural cell id; needs no geometry.
        index: 1-based ``(i, j, k)`` of a structured grid.

    Raises:
        ValueError: Unless exactly one of point, ``id`` or ``index`` is given.
    """

    def __init__(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        *,
        id: int | None = None,
        index: Sequence[int] | None = None,
    ) -> None:
        super().__init__(None)
        point = [x, y, z]
        given = [any(v is not None for v in point), id is not None, index is not None]
        if sum(given) != 1:
            raise ValueError("Cell needs exactly one of a point (x, y, z), id or index")
        self.point = [None if v is None else float(v) for v in point]
        self.id = None if id is None else int(id)
        self.index = None if index is None else [int(v) for v in index]

    def options(self) -> dict:
        x, y, z = self.point
        return {"x": x, "y": y, "z": z, "id": self.id, "index": self.index}

    def needs_geometry(self, study: PflotranStudy | None) -> bool:
        return self.id is None

    def cells(
        self, geometry: CellGeometry | None, study: PflotranStudy | None, workdir: Path | None
    ) -> np.ndarray:
        if self.id is not None:
            return _check_ids([self.id], geometry)
        geometry = _need(geometry, "Cell by point or index")
        if self.index is not None:
            if geometry.shape is None:
                raise ValueError("Cell(index=...) needs a structured grid")
            i, j, k = self.index
            nx, ny, nz = geometry.shape
            if not (1 <= i <= nx and 1 <= j <= ny and 1 <= k <= nz):
                raise ValueError(f"index {self.index} is outside the grid {list(geometry.shape)}")
            return np.array([i + (j - 1) * nx + (k - 1) * nx * ny])
        return np.array([_nearest(geometry, self.point)])


class Cells(Selection):
    """Several cells, each reported on its own row (a ``cell`` column tells which).

    Args:
        ids: 1-based natural ids.
        points: ``[x, y, z]`` points; the nearest cell of each.
    """

    per_cell = True

    def __init__(
        self,
        ids: Sequence[int] | None = None,
        points: Sequence[Sequence[float]] | None = None,
    ) -> None:
        super().__init__(None)
        if (ids is None) == (points is None):
            raise ValueError("Cells needs either ids or points")
        self.ids = None if ids is None else [int(v) for v in ids]
        self.points = None if points is None else [[float(v) for v in p] for p in points]

    def options(self) -> dict:
        return {"ids": self.ids, "points": self.points}

    def needs_geometry(self, study: PflotranStudy | None) -> bool:
        return self.ids is None

    def cells(
        self, geometry: CellGeometry | None, study: PflotranStudy | None, workdir: Path | None
    ) -> np.ndarray:
        if self.ids is not None:
            return _check_ids(self.ids, geometry)
        geometry = _need(geometry, "Cells by points")
        return np.array([_nearest(geometry, point) for point in self.points])


def _read_id_file(path: Path, region: str) -> np.ndarray:
    if path.suffix.lower() in (".h5", ".hdf5"):
        with h5py.File(path, "r") as data:
            return np.asarray(data[f"Regions/{region}/Cell Ids"][...], dtype=int)
    tokens = path.read_text().split()
    if tokens and not tokens[0].lstrip("-").isdigit():  # "CELL_IDS <count>" header
        tokens = tokens[2:] if len(tokens) > 1 and tokens[1].isdigit() else tokens[1:]
    try:
        return np.array([int(token) for token in tokens], dtype=int)
    except ValueError as exc:
        raise ValueError(f"{path.name}: expected a list of cell ids") from exc


class Region(Selection):
    """Cells of a deck ``REGION`` or of an explicit box, reduced by an aggregate.

    Deck regions may be ``COORDINATES`` (a box, or one point), ``COORDINATE`` (a point: the
    cell containing it), ``BLOCK i1 i2 j1 j2 k1 k2`` or ``FILE`` (cell ids, text or HDF5).
    On structured grids a box selects the cells it overlaps; a zero-width box (a face such
    as ``REGION west``) selects the cells touching it. On other grids it selects the cells
    whose center lies in it.

    Args:
        name: Deck region name.
        box: ``[[x0, y0, z0], [x1, y1, z1]]`` instead of a deck region.
        aggregate: Required, e.g. ``"volume_mean"``.
    """

    def __init__(
        self,
        name: str | None = None,
        *,
        box: Sequence[Sequence[float]] | None = None,
        aggregate: Aggregate | None = None,
    ) -> None:
        if (name is None) == (box is None):
            raise ValueError("Region needs either a deck region name or a box")
        if aggregate is None:
            raise ValueError(
                f"Region needs an aggregate: one of {sorted(AGGREGATES)} or a function"
            )
        super().__init__(aggregate)
        self.name = name
        self.box = None if box is None else [[float(v) for v in corner] for corner in box]
        if self.box is not None and (len(self.box) != 2 or any(len(c) != 3 for c in self.box)):
            raise ValueError("box must be [[x0, y0, z0], [x1, y1, z1]]")

    def options(self) -> dict:
        return {"name": self.name, "box": self.box, "aggregate": _aggregate_spec(self.aggregate)}

    def _block(self, study: PflotranStudy) -> Any:
        if study is None:
            raise ValueError(f"REGION {self.name!r} needs the study's deck")
        blocks = [c for c in study.deck.find_all(f"REGION {self.name}", blocks_only=True)]
        if not blocks:
            names = [c.name for c in study.deck.find_all("REGION", blocks_only=True)]
            raise ValueError(f"No REGION {self.name!r} in the deck; regions: {names}")
        return blocks[0]

    def needs_geometry(self, study: PflotranStudy | None) -> bool:
        if self.box is not None:
            return True
        keys = {child.key for child in self._block(study).children}
        return "FILE" not in keys

    def validate(self, geometry: CellGeometry | None, study: PflotranStudy) -> None:
        if self.name is not None:
            self._block(study)  # the region must exist even when the grid is unknown
        super().validate(geometry, study)

    def cells(
        self, geometry: CellGeometry | None, study: PflotranStudy | None, workdir: Path | None
    ) -> np.ndarray:
        what = f"REGION {self.name}" if self.name else f"box {self.box}"
        if self.box is not None:
            ids = _in_box(_need(geometry, what), *np.array(self.box))
        else:
            ids = self._deck_cells(geometry, study, workdir)
        if len(ids) == 0:
            raise ValueError(f"{what} selects no cell")
        return ids

    def _deck_cells(
        self, geometry: CellGeometry | None, study: PflotranStudy, workdir: Path | None
    ) -> np.ndarray:
        children = {child.key: child for child in self._block(study).children}
        if "FILE" in children:
            path = locate_file(study, children["FILE"].args[0], workdir)
            return np.unique(_check_ids(_read_id_file(path, self.name), geometry))
        geometry = _need(geometry, f"REGION {self.name}")
        if "COORDINATE" in children:
            return np.array([_nearest(geometry, deck_numbers(children["COORDINATE"].args[:3]))])
        if "COORDINATES" in children:
            rows = [deck_numbers([c.keyword, *c.args][:3]) for c in children["COORDINATES"].children]
            if len(rows) == 1:
                return np.array([_nearest(geometry, rows[0])])
            return _in_box(geometry, np.array(rows[0]), np.array(rows[1]))
        if "BLOCK" in children:
            if geometry.shape is None:
                raise ValueError(f"REGION {self.name}: BLOCK needs a structured grid")
            i1, i2, j1, j2, k1, k2 = (int(v) for v in deck_numbers(children["BLOCK"].args[:6]))
            nx, ny, _ = geometry.shape
            return np.array(
                [
                    i + (j - 1) * nx + (k - 1) * nx * ny
                    for k in range(k1, k2 + 1)
                    for j in range(j1, j2 + 1)
                    for i in range(i1, i2 + 1)
                ]
            )
        raise ValueError(f"REGION {self.name}: only COORDINATE(S), BLOCK and FILE are supported")


class Domain(Selection):
    """Every cell of the grid, reduced by an aggregate (``Domain("integral")``: total mass).

    Args:
        aggregate: Required, e.g. ``"volume_mean"``.
    """

    def __init__(self, aggregate: Aggregate) -> None:
        if aggregate is None:
            raise ValueError(f"Domain needs an aggregate: one of {sorted(AGGREGATES)}")
        super().__init__(aggregate)

    def cells(
        self, geometry: CellGeometry | None, study: PflotranStudy | None, workdir: Path | None
    ) -> np.ndarray:
        return np.arange(1, _need(geometry, "Domain").size + 1)
