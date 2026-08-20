"""Indexed triangle-to-cell intersection and geometry-based DFN upscaling."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import tempfile
from typing import Iterator
from functools import lru_cache
import multiprocessing
from multiprocessing import shared_memory
import re

import h5py
import numpy as np
from rtree import index as rtree_index
from scipy.spatial import ConvexHull, QhullError

from pydelling.preprocessing.mesh_preprocessor.array_mesh import ArrayMesh, CELL_FACES
from .surface_dfn import SurfaceDfn


class IntersectionError(RuntimeError):
    """Raised when triangle/cell geometry is invalid."""


@dataclass
class IntersectionTable:
    """Sparse triangle-to-cell intersection areas."""

    triangle_indices: np.ndarray
    cell_indices: np.ndarray
    areas: np.ndarray

    def __post_init__(self) -> None:
        self.triangle_indices = np.asarray(self.triangle_indices, dtype=np.int64)
        self.cell_indices = np.asarray(self.cell_indices, dtype=np.int64)
        self.areas = np.asarray(self.areas, dtype=np.float64)
        if not (
            self.triangle_indices.shape == self.cell_indices.shape == self.areas.shape
        ):
            raise IntersectionError("intersection table arrays have different lengths")


@dataclass(frozen=True)
class IntersectionView:
    """A lightweight view of selected compact intersection records."""

    source_kinds: np.ndarray
    source_ids: np.ndarray
    triangle_indices: np.ndarray
    source_triangle_ids: np.ndarray
    cell_indices: np.ndarray
    cell_ids: np.ndarray
    areas: np.ndarray
    pore_volumes: np.ndarray
    physical_volumes: np.ndarray
    polygons: object = None

    def __len__(self):
        return len(self.areas)


class IntersectionIndex:
    """Compact source- and cell-indexed access to a retained intersection table."""

    def __init__(self, surface: SurfaceDfn, mesh: ArrayMesh, table: IntersectionTable):
        self.surface = surface
        self.mesh = mesh
        self.table = table
        tri = table.triangle_indices
        self.source_kinds = (
            np.full(len(tri), "surface", dtype="U16")
            if surface.source_kinds is None else surface.source_kinds[tri]
        )
        source_object_ids = (
            surface.fracture_element_ids
            if surface.source_object_ids is None else surface.source_object_ids
        )
        source_triangle_ids = (
            np.arange(surface.n_triangles, dtype=np.int64)
            if surface.source_triangle_ids is None else surface.source_triangle_ids
        )
        self.source_ids = source_object_ids[tri]
        self.source_triangle_ids = source_triangle_ids[tri]
        self.cell_ids = mesh.cell_ids[table.cell_indices]
        self.pore_volumes = table.areas * surface.effective_aperture[tri]
        self.physical_volumes = table.areas * surface.thickness[tri]
        self._source_order = np.lexsort((self.source_ids, self.source_kinds))
        self._cell_order = np.argsort(self.cell_ids, kind="stable")
        self._source_slices = self._build_source_slices()
        self._cell_slices = self._build_cell_slices()

    def _build_source_slices(self):
        result = {}
        ordered_kind = self.source_kinds[self._source_order]
        ordered_id = self.source_ids[self._source_order]
        start = 0
        while start < len(self._source_order):
            stop = start + 1
            while stop < len(self._source_order) and ordered_kind[stop] == ordered_kind[start] and ordered_id[stop] == ordered_id[start]:
                stop += 1
            result[(str(ordered_kind[start]), int(ordered_id[start]))] = slice(start, stop)
            start = stop
        return result

    def _build_cell_slices(self):
        result = {}
        ordered = self.cell_ids[self._cell_order]
        start = 0
        while start < len(ordered):
            stop = start + 1
            while stop < len(ordered) and ordered[stop] == ordered[start]:
                stop += 1
            result[int(ordered[start])] = slice(start, stop)
            start = stop
        return result

    def _view(self, records):
        records = np.asarray(records, dtype=np.int64)
        table = self.table
        return IntersectionView(
            source_kinds=self.source_kinds[records],
            source_ids=self.source_ids[records],
            triangle_indices=table.triangle_indices[records],
            source_triangle_ids=self.source_triangle_ids[records],
            cell_indices=table.cell_indices[records],
            cell_ids=self.cell_ids[records],
            areas=table.areas[records],
            pore_volumes=self.pore_volumes[records],
            physical_volumes=self.physical_volumes[records],
        )

    def _source(self, kind: str, source):
        source_id = int(getattr(source, "local_id", source))
        selected = self._source_slices.get((kind, source_id))
        records = np.empty(0, dtype=np.int64) if selected is None else self._source_order[selected]
        return self._view(records)

    def for_fracture(self, fracture_or_id):
        return self._source("fracture", fracture_or_id)

    def for_fault(self, fault_or_id):
        return self._source("fault", fault_or_id)

    def for_cell(self, element_or_id):
        cell_id = int(getattr(element_or_id, "local_id", element_or_id))
        selected = self._cell_slices.get(cell_id)
        records = np.empty(0, dtype=np.int64) if selected is None else self._cell_order[selected]
        return self._view(records)

    def for_pair(self, source, element):
        kind = "fault" if hasattr(source, "meshio_mesh") else "fracture"
        cell_id = int(getattr(element, "local_id", element))
        # Re-select original records to preserve zero-copy numeric slicing where possible.
        selected = self._source_slices.get((kind, int(getattr(source, "local_id", source))))
        records = np.empty(0, dtype=np.int64) if selected is None else self._source_order[selected]
        return self._view(records[self.cell_ids[records] == cell_id])


def _face_plane(vertices: np.ndarray, cell_centroid: np.ndarray) -> tuple[np.ndarray, float]:
    # Newell's method gives a stable plane for triangles and nearly planar quads.
    normal = np.zeros(3, dtype=np.float64)
    for current, following in zip(vertices, np.roll(vertices, -1, axis=0)):
        normal += np.cross(current, following)
    magnitude = np.linalg.norm(normal)
    if magnitude == 0:
        raise IntersectionError("cell contains a degenerate face")
    normal /= magnitude
    face_centroid = vertices.mean(axis=0)
    if np.dot(normal, cell_centroid - face_centroid) > 0:
        normal *= -1
    return normal, -float(np.dot(normal, face_centroid))


def _cell_planes(mesh: ArrayMesh, cell_index: int) -> list[tuple[np.ndarray, float]]:
    code = str(mesh.cell_types[cell_index])
    vertices = mesh.cell_vertices(cell_index)
    planes = [_face_plane(vertices[list(face)], mesh.centroids[cell_index]) for face in CELL_FACES[code]]
    scale = max(float(np.linalg.norm(np.ptp(vertices, axis=0))), 1.0)
    planar = all(
        np.max(np.abs(vertices[list(face)] @ normal + offset)) <= 1.0e-11 * scale
        for face, (normal, offset) in zip(CELL_FACES[code], planes)
    )
    if planar:
        return planes
    # A warped quadrilateral does not define one half-space.  Its convex hull
    # does: Qhull returns the supporting triangular facets with inward points
    # satisfying n.x + d <= 0.
    try:
        hull = ConvexHull(vertices)
    except QhullError as exc:
        raise IntersectionError(f"cell {mesh.cell_ids[cell_index]} is not a valid convex cell") from exc
    equations = hull.equations
    if np.any(equations[:, :3] @ mesh.centroids[cell_index] + equations[:, 3] > 1.0e-9 * scale):
        raise IntersectionError(f"cell {mesh.cell_ids[cell_index]} is non-convex or misordered")
    return [(row[:3], float(row[3])) for row in equations]


def _clip_polygon(
    polygon: np.ndarray,
    planes: list[tuple[np.ndarray, float]],
    tolerance: float,
) -> np.ndarray:
    result = np.asarray(polygon, dtype=np.float64)
    for normal, offset in planes:
        if not len(result):
            break
        distances = result @ normal + offset
        output: list[np.ndarray] = []
        previous = result[-1]
        previous_distance = distances[-1]
        previous_inside = previous_distance <= tolerance
        for current, current_distance in zip(result, distances):
            current_inside = current_distance <= tolerance
            if current_inside != previous_inside:
                denominator = previous_distance - current_distance
                if abs(denominator) > np.finfo(float).eps:
                    weight = previous_distance / denominator
                    output.append(previous + weight * (current - previous))
            if current_inside:
                output.append(current)
            previous = current
            previous_distance = current_distance
            previous_inside = current_inside
        result = np.asarray(output, dtype=np.float64)
    return result


def _polygon_area(polygon: np.ndarray, unit_normal: np.ndarray) -> float:
    if len(polygon) < 3:
        return 0.0
    cross_sum = np.sum(np.cross(polygon, np.roll(polygon, -1, axis=0)), axis=0)
    return abs(float(np.dot(cross_sum, unit_normal))) * 0.5


class CellBoundsIndex:
    """Bulk-loaded spatial index over compact mesh cell bounds."""

    def __init__(self, mesh: ArrayMesh, bounds: np.ndarray | None = None):
        self.mesh = mesh
        properties = rtree_index.Property()
        properties.dimension = 3
        bounds = mesh.cell_bounds if bounds is None else bounds
        self.index = rtree_index.Index(
            ((i, tuple(row), None) for i, row in enumerate(bounds)), properties=properties
        )

        # Repeated triangles generally touch the same small set of cells.
        # Caching avoids reconstructing face planes in the inner loop while
        # keeping a strict cap for full-model memory use.
        self.planes = lru_cache(maxsize=100_000)(self._planes)

    def _planes(self, cell_index: int):
        return _cell_planes(self.mesh, cell_index)

    def query(self, bounds: np.ndarray) -> Iterator[int]:
        return self.index.intersection(tuple(map(float, bounds)))


def _intersect_ranges(
    points: np.ndarray,
    connectivity: np.ndarray,
    spatial: CellBoundsIndex,
    ranges: list[tuple[int, int]],
    relative_tolerance: float,
) -> IntersectionTable:
    triangle_out: list[int] = []
    cell_out: list[int] = []
    area_out: list[float] = []
    for start, stop in ranges:
        ids = np.arange(start, stop, dtype=np.int64)
        triangles = points[connectivity[start:stop]]
        cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        magnitudes = np.linalg.norm(cross, axis=1)
        if np.any(magnitudes == 0):
            bad = int(ids[np.flatnonzero(magnitudes == 0)[0]])
            raise IntersectionError(f"triangle {bad} is degenerate")
        normals = cross / magnitudes[:, None]
        source_areas = magnitudes * 0.5
        lows = triangles.min(axis=1)
        highs = triangles.max(axis=1)

        for local, triangle_id in enumerate(ids):
            triangle = triangles[local]
            scale = max(float(np.linalg.norm(highs[local] - lows[local])), 1.0)
            tolerance = relative_tolerance * scale
            query_bounds = np.concatenate((lows[local] - tolerance, highs[local] + tolerance))
            candidate_cells: list[int] = []
            candidate_areas: list[float] = []
            for cell_index in spatial.query(query_bounds):
                clipped = _clip_polygon(
                    triangle,
                    spatial.planes(int(cell_index)),
                    tolerance,
                )
                area = _polygon_area(clipped, normals[local])
                if area > tolerance * tolerance:
                    candidate_cells.append(int(cell_index))
                    candidate_areas.append(area)
            if not candidate_areas:
                continue
            values = np.asarray(candidate_areas, dtype=np.float64)
            total = float(values.sum())
            if total > source_areas[local] * (1.0 + 10 * relative_tolerance):
                values *= source_areas[local] / total
            triangle_out.extend([int(triangle_id)] * len(candidate_cells))
            cell_out.extend(candidate_cells)
            area_out.extend(values.tolist())
    return IntersectionTable(triangle_out, cell_out, area_out)


_WORKER_ARRAYS: dict[str, np.ndarray] = {}
_WORKER_MEMORY: list[shared_memory.SharedMemory] = []
_WORKER_INDEX: CellBoundsIndex | None = None


def _attach_shared(descriptors):
    global _WORKER_ARRAYS, _WORKER_MEMORY, _WORKER_INDEX
    _WORKER_ARRAYS = {}
    _WORKER_MEMORY = []
    for name, shared_name, shape, dtype in descriptors:
        memory = shared_memory.SharedMemory(name=shared_name)
        _WORKER_MEMORY.append(memory)
        _WORKER_ARRAYS[name] = np.ndarray(shape, dtype=np.dtype(dtype), buffer=memory.buf)
    mesh = ArrayMesh(
        points=_WORKER_ARRAYS["mesh_points"],
        connectivity=_WORKER_ARRAYS["mesh_connectivity"],
        cell_types=_WORKER_ARRAYS["mesh_cell_types"],
        cell_ids=_WORKER_ARRAYS["mesh_cell_ids"],
        centroids=_WORKER_ARRAYS["mesh_centroids"],
        volumes=_WORKER_ARRAYS["mesh_volumes"],
        point_ids=_WORKER_ARRAYS["mesh_point_ids"],
    )
    _WORKER_INDEX = CellBoundsIndex(mesh, bounds=_WORKER_ARRAYS["mesh_bounds"])


def _worker_intersect(task):
    ranges, relative_tolerance = task
    return _intersect_ranges(
        _WORKER_ARRAYS["surface_points"],
        _WORKER_ARRAYS["surface_triangles"],
        _WORKER_INDEX,
        ranges,
        relative_tolerance,
    )


class _SharedArrays:
    def __init__(self, arrays: dict[str, np.ndarray]):
        self.memory = []
        self.descriptors = []
        for name, values in arrays.items():
            values = np.ascontiguousarray(values)
            memory = shared_memory.SharedMemory(create=True, size=values.nbytes)
            np.ndarray(values.shape, dtype=values.dtype, buffer=memory.buf)[:] = values
            self.memory.append(memory)
            self.descriptors.append((name, memory.name, values.shape, values.dtype.str))

    def close(self):
        for memory in self.memory:
            memory.close()
            memory.unlink()


def _new_accumulators(surface: SurfaceDfn, mesh: ArrayMesh, group_contributions: bool):
    groups = (
        {int(group): np.zeros(mesh.n_cells, dtype=np.float64) for group in np.unique(surface.group_ids)}
        if group_contributions
        else {}
    )
    return {
        "area": np.zeros(mesh.n_cells, dtype=np.float64),
        "pore_volume": np.zeros(mesh.n_cells, dtype=np.float64),
        "physical_volume": np.zeros(mesh.n_cells, dtype=np.float64),
        "dfn_storage": np.zeros(mesh.n_cells, dtype=np.float64),
        "count": np.zeros(mesh.n_cells, dtype=np.int64),
        "dfn_K": np.zeros((mesh.n_cells, 3, 3), dtype=np.float64),
        "group_volume": groups,
    }


def _accumulate_table(surface, mesh, table, accumulators, normals):
    tri = table.triangle_indices
    cell = table.cell_indices
    area = table.areas
    if not len(area):
        return
    aperture = surface.effective_aperture
    transmissivity = surface.plane_transmissivity
    np.add.at(accumulators["area"], cell, area)
    np.add.at(accumulators["pore_volume"], cell, area * aperture[tri])
    physical_volume = area * surface.thickness[tri]
    np.add.at(accumulators["physical_volume"], cell, physical_volume)
    np.add.at(
        accumulators["dfn_storage"],
        cell,
        physical_volume * surface.specific_storage[tri] / mesh.volumes[cell],
    )
    np.add.at(accumulators["count"], cell, 1)
    projectors = np.eye(3)[None, :, :] - normals[tri, :, None] * normals[tri, None, :]
    weights = area * transmissivity[tri] / mesh.volumes[cell]
    contributions = projectors * weights[:, None, None]
    for i in range(3):
        for j in range(3):
            np.add.at(accumulators["dfn_K"][:, i, j], cell, contributions[:, i, j])
    for group_id, volume in accumulators["group_volume"].items():
        selected = surface.group_ids[tri] == group_id
        np.add.at(volume, cell[selected], area[selected] * aperture[tri[selected]])


def accumulate_surface_with_mesh(
    surface: SurfaceDfn,
    mesh: ArrayMesh,
    *,
    chunk_size: int = 50_000,
    relative_tolerance: float = 1.0e-9,
    workers: int = 1,
    group_contributions: bool = True,
):
    """Stream intersections into cell arrays without retaining sparse details."""

    ranges = [(chunk.start, chunk.stop) for chunk in surface.iter_chunks(chunk_size)]
    triangle_xyz = surface.points[surface.triangles]
    cross = np.cross(
        triangle_xyz[:, 1] - triangle_xyz[:, 0],
        triangle_xyz[:, 2] - triangle_xyz[:, 0],
    )
    magnitudes = np.linalg.norm(cross, axis=1)
    if np.any(magnitudes == 0):
        raise IntersectionError(f"triangle {int(np.flatnonzero(magnitudes == 0)[0])} is degenerate")
    normals = cross / magnitudes[:, None]
    accumulators = _new_accumulators(surface, mesh, group_contributions)
    if workers == 1 or len(ranges) <= 1:
        spatial = CellBoundsIndex(mesh)
        for current in ranges:
            table = _intersect_ranges(
                surface.points, surface.triangles, spatial, [current], relative_tolerance
            )
            _accumulate_table(surface, mesh, table, accumulators, normals)
        return accumulators

    if workers < 1:
        raise ValueError("workers must be at least one")
    shared = _SharedArrays(
        {
            "mesh_points": mesh.points,
            "mesh_connectivity": mesh.connectivity,
            "mesh_cell_types": mesh.cell_types,
            "mesh_cell_ids": mesh.cell_ids,
            "mesh_centroids": mesh.centroids,
            "mesh_volumes": mesh.volumes,
            "mesh_point_ids": mesh.point_ids,
            "mesh_bounds": mesh.cell_bounds,
            "surface_points": surface.points,
            "surface_triangles": surface.triangles,
        }
    )
    try:
        context = multiprocessing.get_context("spawn")
        tasks = (([current], relative_tolerance) for current in ranges)
        with context.Pool(
            processes=workers,
            initializer=_attach_shared,
            initargs=(shared.descriptors,),
        ) as pool:
            for table in pool.imap(_worker_intersect, tasks):
                _accumulate_table(surface, mesh, table, accumulators, normals)
    finally:
        shared.close()
    return accumulators


def intersect_surface_with_mesh(
    surface: SurfaceDfn,
    mesh: ArrayMesh,
    *,
    chunk_size: int = 50_000,
    relative_tolerance: float = 1.0e-9,
    workers: int = 1,
) -> IntersectionTable:
    """Intersect every surface triangle with candidate convex mesh cells.

    Area duplicated by a triangle lying on a shared cell face is normalized
    conservatively across the coincident cells.
    """

    if relative_tolerance <= 0:
        raise ValueError("relative_tolerance must be positive")
    if workers < 1:
        raise ValueError("workers must be at least one")
    ranges = [(chunk.start, chunk.stop) for chunk in surface.iter_chunks(chunk_size)]
    if workers == 1 or len(ranges) <= 1:
        return _intersect_ranges(
            surface.points,
            surface.triangles,
            CellBoundsIndex(mesh),
            ranges,
            relative_tolerance,
        )

    shared = _SharedArrays(
        {
            "mesh_points": mesh.points,
            "mesh_connectivity": mesh.connectivity,
            "mesh_cell_types": mesh.cell_types,
            "mesh_cell_ids": mesh.cell_ids,
            "mesh_centroids": mesh.centroids,
            "mesh_volumes": mesh.volumes,
            "mesh_point_ids": mesh.point_ids,
            "mesh_bounds": mesh.cell_bounds,
            "surface_points": surface.points,
            "surface_triangles": surface.triangles,
        }
    )
    try:
        tasks = [([current], relative_tolerance) for current in ranges]
        context = multiprocessing.get_context("spawn")
        with context.Pool(
            processes=workers,
            initializer=_attach_shared,
            initargs=(shared.descriptors,),
        ) as pool:
            tables = pool.map(_worker_intersect, tasks)
    finally:
        shared.close()
    if not tables:
        return IntersectionTable([], [], [])
    return IntersectionTable(
        np.concatenate([table.triangle_indices for table in tables]),
        np.concatenate([table.cell_indices for table in tables]),
        np.concatenate([table.areas for table in tables]),
    )


def _scalar_field(values, size: int, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 0:
        return np.full(size, float(array), dtype=np.float64)
    if array.shape != (size,):
        raise ValueError(f"{name} must be a scalar or have shape ({size},)")
    return array.copy()


def _tensor_field(values, size: int, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 0:
        result = np.zeros((size, 3, 3), dtype=np.float64)
        result[:, range(3), range(3)] = float(array)
        return result
    if array.shape == (size,):
        result = np.zeros((size, 3, 3), dtype=np.float64)
        result[:, range(3), range(3)] = array[:, None]
        return result
    if array.shape == (3, 3):
        return np.broadcast_to(array, (size, 3, 3)).copy()
    if array.shape != (size, 3, 3):
        raise ValueError(f"{name} must be scalar, (n,), (3,3), or (n,3,3)")
    return array.copy()


@dataclass
class UpscalingResult:
    """Cell-aligned DFN upscaling fields and export helpers."""

    mesh: ArrayMesh
    matrix_porosity: np.ndarray
    dfn_porosity: np.ndarray
    porosity: np.ndarray
    matrix_specific_storage: np.ndarray
    dfn_specific_storage: np.ndarray
    specific_storage: np.ndarray
    matrix_hydraulic_conductivity: np.ndarray
    dfn_hydraulic_conductivity: np.ndarray
    hydraulic_conductivity: np.ndarray
    matrix_intrinsic_permeability: np.ndarray
    dfn_intrinsic_permeability: np.ndarray
    intrinsic_permeability: np.ndarray
    fracture_area: np.ndarray
    fracture_pore_volume: np.ndarray
    fracture_element_count: np.ndarray
    group_porosity: dict[int, np.ndarray] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    @staticmethod
    def _tensor_arrays(prefix: str, values: np.ndarray) -> dict[str, np.ndarray]:
        return {
            f"{prefix}_xx": values[:, 0, 0],
            f"{prefix}_xy": values[:, 0, 1],
            f"{prefix}_xz": values[:, 0, 2],
            f"{prefix}_yy": values[:, 1, 1],
            f"{prefix}_yz": values[:, 1, 2],
            f"{prefix}_zz": values[:, 2, 2],
        }

    def vtk_cell_data(self, *, include_group_contributions: bool = True) -> dict[str, np.ndarray]:
        data = {
            "source_cell_id": self.mesh.cell_ids,
            "matrix_porosity": self.matrix_porosity,
            "dfn_porosity": self.dfn_porosity,
            "porosity": self.porosity,
            "matrix_specific_storage": self.matrix_specific_storage,
            "dfn_specific_storage": self.dfn_specific_storage,
            "specific_storage": self.specific_storage,
            "fracture_area": self.fracture_area,
            "fracture_pore_volume": self.fracture_pore_volume,
            "fracture_element_count": self.fracture_element_count,
        }
        if self.mesh.material_ids is not None:
            data["material_id"] = self.mesh.material_ids
        for metadata_name in (
            "density_kg_m3",
            "dynamic_viscosity_pa_s",
            "gravity_m_s2",
        ):
            if metadata_name in self.metadata:
                data[metadata_name] = np.full(
                    self.mesh.n_cells, float(self.metadata[metadata_name]), dtype=float
                )
        data.update(self._tensor_arrays("matrix_hydraulic_conductivity", self.matrix_hydraulic_conductivity))
        data.update(self._tensor_arrays("dfn_hydraulic_conductivity", self.dfn_hydraulic_conductivity))
        data.update(self._tensor_arrays("hydraulic_conductivity", self.hydraulic_conductivity))
        data.update(self._tensor_arrays("matrix_permeability", self.matrix_intrinsic_permeability))
        data.update(self._tensor_arrays("dfn_permeability", self.dfn_intrinsic_permeability))
        data.update(self._tensor_arrays("permeability", self.intrinsic_permeability))
        if include_group_contributions:
            names = self.metadata.get("dfn_groups", {})
            for group_id, values in self.group_porosity.items():
                label = re.sub(
                    r"[^A-Za-z0-9_]", "_", str(names.get(group_id, f"group_{group_id}"))
                )
                data[f"dfn_porosity_{label}"] = values
        return data

    def to_vtk(self, filename: str | Path, *, include_group_contributions: bool = True) -> Path:
        return self.mesh.write_vtk(
            filename, self.vtk_cell_data(include_group_contributions=include_group_contributions)
        )

    def to_pflotran_hdf5(self, filename: str | Path) -> Path:
        """Write simulation fields and QA/provenance into one atomic HDF5 file."""

        path = Path(filename).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".h5", delete=False) as handle:
                temporary = Path(handle.name)
            with h5py.File(temporary, "w") as output:
                output.create_dataset("Cell Ids", data=self.mesh.cell_ids)
                output.create_dataset("Porosity", data=self.porosity)
                output.create_dataset("Specific Storage", data=self.specific_storage)
                mapping = {
                    "PermeabilityX": (0, 0),
                    "PermeabilityXY": (0, 1),
                    "PermeabilityXZ": (0, 2),
                    "PermeabilityY": (1, 1),
                    "PermeabilityYZ": (1, 2),
                    "PermeabilityZ": (2, 2),
                }
                for name, (i, j) in mapping.items():
                    output.create_dataset(name, data=self.intrinsic_permeability[:, i, j])
                qa = output.create_group("QA")
                for name, values in self.vtk_cell_data().items():
                    qa.create_dataset(name, data=values)
                for key, value in self.metadata.items():
                    output.attrs[key] = json.dumps(value) if isinstance(value, (dict, list, tuple)) else value
            temporary.replace(path)
        except Exception:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise
        return path


def upscale_surface_dfn(
    surface: SurfaceDfn,
    mesh: ArrayMesh,
    *,
    matrix_porosity,
    matrix_intrinsic_permeability,
    matrix_specific_storage=0.0,
    density: float = 997.16,
    dynamic_viscosity: float = 8.9e-4,
    gravity: float = 9.80665,
    intersections: IntersectionTable | None = None,
    chunk_size: int = 50_000,
    workers: int = 1,
    group_contributions: bool = True,
    combination_mode: str = "volume_weighted",
) -> UpscalingResult:
    """Apply Pydelling's geometry-based porosity and full-tensor equations.

    ``volume_weighted`` treats the fracture volume as replacing matrix volume.
    ``additive`` preserves the supplied matrix fields as the base state and adds
    the DFN porosity, storage, and conductivity increments cell by cell.
    """

    if density <= 0 or dynamic_viscosity <= 0 or gravity <= 0:
        raise ValueError("fluid density, viscosity, and gravity must be positive")
    if combination_mode not in ("volume_weighted", "additive"):
        raise ValueError("combination_mode must be 'volume_weighted' or 'additive'")
    n_cells = mesh.n_cells
    matrix_phi = _scalar_field(matrix_porosity, n_cells, "matrix_porosity")
    matrix_storage = _scalar_field(matrix_specific_storage, n_cells, "matrix_specific_storage")
    if np.any(matrix_storage < 0):
        raise ValueError("matrix_specific_storage must be non-negative")
    if np.any(matrix_phi < 0) or np.any(matrix_phi > 1):
        raise ValueError("matrix porosity must lie in [0, 1]")
    matrix_k = _tensor_field(
        matrix_intrinsic_permeability, n_cells, "matrix_intrinsic_permeability"
    )
    triangle_xyz = surface.points[surface.triangles]
    cross = np.cross(triangle_xyz[:, 1] - triangle_xyz[:, 0], triangle_xyz[:, 2] - triangle_xyz[:, 0])
    normals = cross / np.linalg.norm(cross, axis=1)[:, None]
    if intersections is None:
        accumulators = accumulate_surface_with_mesh(
            surface,
            mesh,
            chunk_size=chunk_size,
            workers=workers,
            group_contributions=group_contributions,
        )
        intersection_count = int(accumulators["count"].sum())
    else:
        accumulators = _new_accumulators(surface, mesh, group_contributions)
        _accumulate_table(surface, mesh, intersections, accumulators, normals)
        intersection_count = len(intersections.areas)
    fracture_area = accumulators["area"]
    pore_volume = accumulators["pore_volume"]
    physical_volume = accumulators["physical_volume"]
    element_count = accumulators["count"]
    dfn_phi = pore_volume / mesh.volumes
    if np.any(dfn_phi > 1.0 + 1.0e-10):
        bad = int(mesh.cell_ids[np.argmax(dfn_phi)])
        raise ValueError(f"DFN porosity exceeds one in source cell {bad}")
    dfn_phi = np.minimum(dfn_phi, 1.0)
    if combination_mode == "additive":
        combined_phi = matrix_phi + dfn_phi
    else:
        combined_phi = matrix_phi * (1.0 - dfn_phi) + dfn_phi
    if np.any(combined_phi > 1.0 + 1.0e-10):
        bad = int(mesh.cell_ids[np.argmax(combined_phi)])
        raise ValueError(f"combined porosity exceeds one in source cell {bad}")
    physical_fraction = physical_volume / mesh.volumes
    overfilled_physical_cells = int(np.count_nonzero(physical_fraction > 1.0))
    physical_fraction = np.minimum(physical_fraction, 1.0)
    dfn_storage = accumulators["dfn_storage"]
    if combination_mode == "additive":
        combined_storage = matrix_storage + dfn_storage
    else:
        combined_storage = dfn_storage + matrix_storage * (1.0 - physical_fraction)

    dfn_K = accumulators["dfn_K"]

    conversion = density * gravity / dynamic_viscosity
    matrix_K = matrix_k * conversion
    if combination_mode == "additive":
        combined_K = matrix_K + dfn_K
    else:
        combined_K = dfn_K + matrix_K * (1.0 - dfn_phi)[:, None, None]
    dfn_k = dfn_K / conversion
    combined_k = combined_K / conversion

    group_phi = {
        group_id: volume / mesh.volumes
        for group_id, volume in accumulators["group_volume"].items()
    }

    return UpscalingResult(
        mesh=mesh,
        matrix_porosity=matrix_phi,
        dfn_porosity=dfn_phi,
        porosity=combined_phi,
        matrix_specific_storage=matrix_storage,
        dfn_specific_storage=dfn_storage,
        specific_storage=combined_storage,
        matrix_hydraulic_conductivity=matrix_K,
        dfn_hydraulic_conductivity=dfn_K,
        hydraulic_conductivity=combined_K,
        matrix_intrinsic_permeability=matrix_k,
        dfn_intrinsic_permeability=dfn_k,
        intrinsic_permeability=combined_k,
        fracture_area=fracture_area,
        fracture_pore_volume=pore_volume,
        fracture_element_count=element_count,
        group_porosity=group_phi,
        metadata={
            "density_kg_m3": density,
            "dynamic_viscosity_pa_s": dynamic_viscosity,
            "gravity_m_s2": gravity,
            "dfn_groups": surface.group_names,
            "dfn_metadata": surface.metadata,
            "intersection_count": intersection_count,
            "physical_fraction_clipped_cells": overfilled_physical_cells,
            "combination_mode": combination_mode,
        },
    )
