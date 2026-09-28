"""Array-backed triangulated DFNs and NWMO HydroGeoSphere readers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import mmap
import re
from typing import Iterator

import meshio
import numpy as np


HGS_COLUMNS = (
    "FracElem_ID",
    "ElemNode1",
    "ElemNode2",
    "ElemNode3",
    "Thickness",
    "Hydraulic_Conductivity",
    "Porosity",
    "Specific_Storage",
)
HGS_VARIANTS = ("0.01", "0.1", "0.3", "aperture")


class SurfaceDfnError(ValueError):
    """Raised when a surface DFN is incomplete or inconsistent."""


@dataclass(frozen=True)
class HgsGroup:
    group_id: int
    name: str
    path: Path
    element_count: int


@dataclass
class SurfaceDfn:
    """A triangulated fracture network with one property value per triangle."""

    points: np.ndarray
    triangles: np.ndarray
    thickness: np.ndarray
    hydraulic_conductivity: np.ndarray
    porosity: np.ndarray
    specific_storage: np.ndarray
    group_ids: np.ndarray
    fracture_element_ids: np.ndarray
    group_names: dict[int, str] = field(default_factory=dict)
    source_node_ids: np.ndarray | None = None
    source_kinds: np.ndarray | None = None
    source_object_ids: np.ndarray | None = None
    source_triangle_ids: np.ndarray | None = None
    property_origins: np.ndarray | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.points = np.asarray(self.points, dtype=np.float64)
        self.triangles = np.asarray(self.triangles, dtype=np.int64)
        n = len(self.triangles)
        if self.points.ndim != 2 or self.points.shape[1] != 3:
            raise SurfaceDfnError("points must have shape (n, 3)")
        if self.triangles.shape != (n, 3):
            raise SurfaceDfnError("triangles must have shape (n, 3)")
        for name in (
            "thickness",
            "hydraulic_conductivity",
            "porosity",
            "specific_storage",
            "group_ids",
            "fracture_element_ids",
        ):
            values = np.asarray(getattr(self, name))
            if values.shape != (n,):
                raise SurfaceDfnError(f"{name} must have one value per triangle")
            setattr(self, name, values)
        self.group_ids = self.group_ids.astype(np.int32, copy=False)
        self.fracture_element_ids = self.fracture_element_ids.astype(np.int64, copy=False)
        for name in ("thickness", "hydraulic_conductivity", "porosity", "specific_storage"):
            setattr(self, name, np.asarray(getattr(self, name), dtype=np.float64))
        if np.any(self.triangles < 0) or np.any(self.triangles >= len(self.points)):
            raise SurfaceDfnError("triangle connectivity references a missing point")
        if np.any(self.thickness <= 0) or np.any(self.hydraulic_conductivity < 0):
            raise SurfaceDfnError("thickness must be positive and conductivity non-negative")
        if np.any(self.porosity < 0) or np.any(self.porosity > 1):
            raise SurfaceDfnError("fracture porosity must lie in [0, 1]")
        if self.source_node_ids is not None:
            self.source_node_ids = np.asarray(self.source_node_ids, dtype=np.int64)
            if self.source_node_ids.shape != (len(self.points),):
                raise SurfaceDfnError("source_node_ids must have one value per point")
        optional_triangle_fields = {
            "source_kinds": "U16",
            "source_object_ids": np.int64,
            "source_triangle_ids": np.int64,
            "property_origins": "U512",
        }
        for name, dtype in optional_triangle_fields.items():
            values = getattr(self, name)
            if values is None:
                continue
            values = np.asarray(values, dtype=dtype)
            if values.shape != (n,):
                raise SurfaceDfnError(f"{name} must have one value per triangle")
            setattr(self, name, values)

    @property
    def n_triangles(self) -> int:
        return len(self.triangles)

    @property
    def effective_aperture(self) -> np.ndarray:
        return self.thickness * self.porosity

    @property
    def plane_transmissivity(self) -> np.ndarray:
        return self.thickness * self.hydraulic_conductivity

    def iter_chunks(self, chunk_size: int = 50_000) -> Iterator[slice]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        for start in range(0, self.n_triangles, chunk_size):
            yield slice(start, min(start + chunk_size, self.n_triangles))

    def subset(
        self, bounds: tuple[float, float, float, float, float, float]
    ) -> "SurfaceDfn":
        xmin, xmax, ymin, ymax, zmin, zmax = map(float, bounds)
        xyz = self.points[self.triangles]
        low = xyz.min(axis=1)
        high = xyz.max(axis=1)
        keep = (
            (high[:, 0] >= xmin)
            & (low[:, 0] <= xmax)
            & (high[:, 1] >= ymin)
            & (low[:, 1] <= ymax)
            & (high[:, 2] >= zmin)
            & (low[:, 2] <= zmax)
        )
        ids = np.flatnonzero(keep)
        used, inverse = np.unique(self.triangles[ids], return_inverse=True)
        return SurfaceDfn(
            points=self.points[used],
            triangles=inverse.reshape(-1, 3),
            thickness=self.thickness[ids],
            hydraulic_conductivity=self.hydraulic_conductivity[ids],
            porosity=self.porosity[ids],
            specific_storage=self.specific_storage[ids],
            group_ids=self.group_ids[ids],
            fracture_element_ids=self.fracture_element_ids[ids],
            group_names=dict(self.group_names),
            source_node_ids=None if self.source_node_ids is None else self.source_node_ids[used],
            source_kinds=None if self.source_kinds is None else self.source_kinds[ids],
            source_object_ids=None if self.source_object_ids is None else self.source_object_ids[ids],
            source_triangle_ids=None if self.source_triangle_ids is None else self.source_triangle_ids[ids],
            property_origins=None if self.property_origins is None else self.property_origins[ids],
            metadata=dict(self.metadata),
        )

    def to_meshio(self) -> meshio.Mesh:
        cell_data = {
            "thickness": [self.thickness],
            "hydraulic_conductivity": [self.hydraulic_conductivity],
            "porosity": [self.porosity],
            "specific_storage": [self.specific_storage],
            "dfn_id": [self.group_ids],
            "fracture_element_id": [self.fracture_element_ids],
        }
        point_data = {}
        if self.source_node_ids is not None:
            point_data["source_node_id"] = self.source_node_ids
        field_data = {
            f"dfn_id_{group_id}__{re.sub(r'[^A-Za-z0-9_]', '_', name)}": np.asarray(
                [group_id, 2], dtype=np.int32
            )
            for group_id, name in self.group_names.items()
        }
        return meshio.Mesh(
            self.points,
            [("triangle", self.triangles)],
            cell_data=cell_data,
            point_data=point_data,
            field_data=field_data,
        )

    def write_vtk(self, filename: str | Path) -> Path:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_meshio().write(path)
        return path


def _hgs_metadata(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig") as handle:
        if handle.readline().strip().lower() != "number of fracture elements":
            raise SurfaceDfnError(f"{path}: invalid HGS marker")
        try:
            count = int(handle.readline())
        except ValueError as exc:
            raise SurfaceDfnError(f"{path}: invalid HGS element count") from exc
        columns = tuple(handle.readline().split())
    if tuple(x.lower() for x in columns) != tuple(x.lower() for x in HGS_COLUMNS):
        raise SurfaceDfnError(f"{path}: unexpected HGS columns")
    return count


def discover_hgs_groups(
    directory: str | Path,
    *,
    variant: str = "aperture",
    groups: str | list[str] = "physical",
) -> list[HgsGroup]:
    """Discover one HGS property scenario with a stable group ordering."""

    if variant not in HGS_VARIANTS:
        raise SurfaceDfnError(f"unknown HGS variant {variant!r}")
    directory = Path(directory).expanduser().resolve()
    suffix = f"_{variant}"
    paths = sorted(path for path in directory.glob("*.hgs") if path.stem.endswith(suffix))
    if groups == "physical":
        # AllSets is a strict superset of these three SSDFN extraction files.
        paths = [path for path in paths if not path.stem.startswith("SSDFN_FracFace_Set")]
    elif groups != "all":
        requested = set(groups)
        paths = [path for path in paths if path.stem[: -len(suffix)] in requested]
        missing = requested - {path.stem[: -len(suffix)] for path in paths}
        if missing:
            raise SurfaceDfnError(f"missing HGS groups: {sorted(missing)}")
    if not paths:
        raise SurfaceDfnError(f"no {variant!r} HGS files found in {directory}")
    return [
        HgsGroup(i, path.stem[: -len(suffix)], path, _hgs_metadata(path))
        for i, path in enumerate(paths)
    ]


def _read_hgs_group(group: HgsGroup, target: slice, arrays: dict[str, np.ndarray]) -> None:
    with group.path.open("r", encoding="utf-8-sig") as handle:
        handle.readline()
        handle.readline()
        handle.readline()
        row = target.start
        for local_index in range(group.element_count):
            fields = handle.readline().split()
            if len(fields) != 8:
                raise SurfaceDfnError(f"{group.path}: invalid row {local_index + 4}")
            try:
                arrays["element_id"][row] = int(fields[0])
                arrays["source_nodes"][row] = tuple(map(int, fields[1:4]))
                arrays["thickness"][row] = float(fields[4])
                arrays["conductivity"][row] = float(fields[5])
                arrays["porosity"][row] = float(fields[6])
                arrays["storage"][row] = float(fields[7])
                arrays["group_id"][row] = group.group_id
            except ValueError as exc:
                raise SurfaceDfnError(f"{group.path}: invalid row {local_index + 4}") from exc
            row += 1
        if any(line.strip() for line in handle):
            raise SurfaceDfnError(f"{group.path}: rows exist after the declared count")


def _iter_hgs_rows(path: Path):
    count = _hgs_metadata(path)
    with path.open("r", encoding="utf-8-sig") as handle:
        for _ in range(3):
            handle.readline()
        for row in range(count):
            fields = handle.readline().split()
            if len(fields) != 8:
                raise SurfaceDfnError(f"{path}: invalid row {row + 4}")
            yield (
                int(fields[0]),
                int(fields[1]),
                int(fields[2]),
                int(fields[3]),
                float(fields[4]),
                float(fields[5]),
                float(fields[6]),
                float(fields[7]),
            )


def validate_hgs_directory(
    directory: str | Path,
    *,
    validate_variants: bool = True,
    validate_ssdfn_overlap: bool = True,
) -> dict[str, object]:
    """Validate cross-scenario geometry and the known SSDFN subset overlap.

    This audit is intentionally separate from normal ingestion because checking
    every scenario multiplies I/O and the SSDFN overlap index can be large.
    """

    directory = Path(directory).expanduser().resolve()
    files: dict[str, dict[str, Path]] = {}
    for path in directory.glob("*.hgs"):
        for variant in HGS_VARIANTS:
            suffix = f"_{variant}"
            if path.stem.endswith(suffix):
                files.setdefault(path.stem[: -len(suffix)], {})[variant] = path
                break
    report: dict[str, object] = {"groups": len(files), "variants_checked": 0}
    if validate_variants:
        for name, variants in files.items():
            reference = variants.get("aperture")
            if reference is None:
                raise SurfaceDfnError(f"HGS group {name} has no aperture variant")
            reference_count = _hgs_metadata(reference)
            for variant, candidate in variants.items():
                if candidate == reference:
                    continue
                if _hgs_metadata(candidate) != reference_count:
                    raise SurfaceDfnError(f"{candidate}: count differs from aperture variant")
                for row, (base, other) in enumerate(
                    zip(_iter_hgs_rows(reference), _iter_hgs_rows(candidate), strict=True), start=4
                ):
                    # Fixed scenarios may change porosity only.
                    if base[:6] + base[7:] != other[:6] + other[7:]:
                        raise SurfaceDfnError(
                            f"{candidate}:{row}: variant changes geometry or non-porosity properties"
                        )
                report["variants_checked"] = int(report["variants_checked"]) + 1
    if validate_ssdfn_overlap:
        all_sets = files.get("SSDFN_FracFace_AllSets_015", {}).get("aperture")
        subsets = [
            variants["aperture"]
            for name, variants in files.items()
            if name.startswith("SSDFN_FracFace_Set") and "aperture" in variants
        ]
        overlap_count = 0
        if all_sets is not None and subsets:
            all_properties = {
                tuple(sorted(row[1:4])): row[4:]
                for row in _iter_hgs_rows(all_sets)
            }
            for subset in subsets:
                for row_index, row in enumerate(_iter_hgs_rows(subset), start=4):
                    key = tuple(sorted(row[1:4]))
                    if key not in all_properties or all_properties[key] != row[4:]:
                        raise SurfaceDfnError(
                            f"{subset}:{row_index}: triangle is absent from AllSets or has different properties"
                        )
                    overlap_count += 1
        report["ssdfn_subset_triangles"] = overlap_count
    return report


def _validate_triangle_pairs(source_nodes: np.ndarray, properties: tuple[np.ndarray, ...]) -> None:
    if len(source_nodes) % 2:
        raise SurfaceDfnError("HGS triangle count is not divisible into face pairs")
    first = source_nodes[0::2]
    second = source_nodes[1::2]
    combined = np.concatenate((first, second), axis=1)
    # Every pair represents a quadrilateral: four unique nodes, two shared nodes.
    ordered = np.sort(combined, axis=1)
    unique_counts = 1 + np.sum(ordered[:, 1:] != ordered[:, :-1], axis=1)
    shared = np.sum(first[:, :, None] == second[:, None, :], axis=(1, 2))
    if np.any(unique_counts != 4) or np.any(shared != 2):
        raise SurfaceDfnError("consecutive HGS triangles do not form quadrilateral faces")
    for values in properties:
        if not np.allclose(values[0::2], values[1::2], rtol=0.0, atol=0.0):
            raise SurfaceDfnError("paired HGS triangles have different properties")


def _read_structured_vertices(path: str | Path) -> tuple[np.ndarray, int, int, int]:
    path = Path(path).expanduser().resolve()
    with path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
        offset = mapped.find(b"\nVERTICES ")
        if offset < 0:
            raise SurfaceDfnError(f"{path}: VERTICES section not found")
        mapped.seek(offset + 1)
        header = mapped.readline().split()
        count = int(header[1])
        points = np.empty((count, 3), dtype=np.float64)
        for index in range(count):
            fields = mapped.readline().split()
            if len(fields) != 3:
                raise SurfaceDfnError(f"{path}: invalid vertex {index + 1}")
            points[index] = tuple(map(float, fields))
    first = points[0, :2]
    repeats = np.flatnonzero(np.all(np.isclose(points[1:, :2], first, atol=1e-8, rtol=0), axis=1))
    if not len(repeats):
        raise SurfaceDfnError("could not infer structured mesh layers")
    layer_size = int(repeats[0] + 1)
    first_y = points[0, 1]
    nx = int(np.argmax(~np.isclose(points[:layer_size, 1], first_y, atol=1e-8, rtol=0)))
    if nx == 0:
        raise SurfaceDfnError("could not infer structured x dimension")
    if layer_size % nx or count % layer_size:
        raise SurfaceDfnError("inconsistent structured mesh dimensions")
    return points, nx, layer_size // nx, count // layer_size


def _interpolate_source_nodes(
    source_ids: np.ndarray,
    coarse_points: np.ndarray,
    nx: int,
    ny: int,
    nz: int,
    refinement: int,
) -> np.ndarray:
    fine_nx = (nx - 1) * refinement + 1
    fine_ny = (ny - 1) * refinement + 1
    fine_layer = fine_nx * fine_ny
    zero = source_ids.astype(np.int64) - 1
    k, horizontal = np.divmod(zero, fine_layer)
    fj, fi = np.divmod(horizontal, fine_nx)
    if np.any(k < 0) or np.any(k >= nz) or np.any(fj >= fine_ny):
        raise SurfaceDfnError("HGS node ID lies outside the reconstructed fine grid")
    ci, ri = np.divmod(fi, refinement)
    cj, rj = np.divmod(fj, refinement)
    wx = ri.astype(np.float64) / refinement
    wy = rj.astype(np.float64) / refinement
    x_edge = ci == nx - 1
    y_edge = cj == ny - 1
    ci[x_edge] -= 1
    cj[y_edge] -= 1
    wx[x_edge] = 1.0
    wy[y_edge] = 1.0
    layer_size = nx * ny
    base = k * layer_size + cj * nx + ci
    z00 = coarse_points[base, 2]
    z10 = coarse_points[base + 1, 2]
    z01 = coarse_points[base + nx, 2]
    z11 = coarse_points[base + nx + 1, 2]
    x_axis = coarse_points[:nx, 0]
    y_axis = coarse_points[np.arange(ny) * nx, 1]
    result = np.empty((len(source_ids), 3), dtype=np.float64)
    result[:, 0] = x_axis[ci] * (1 - wx) + x_axis[ci + 1] * wx
    result[:, 1] = y_axis[cj] * (1 - wy) + y_axis[cj + 1] * wy
    result[:, 2] = (
        z00 * (1 - wx) * (1 - wy)
        + z10 * wx * (1 - wy)
        + z01 * (1 - wx) * wy
        + z11 * wx * wy
    )
    return result


def read_hgs_directory(
    directory: str | Path,
    *,
    companion_mesh: str | Path,
    variant: str = "aperture",
    groups: str | list[str] = "physical",
    refinement: int = 4,
    validate_pairs: bool = True,
) -> SurfaceDfn:
    """Read selected HGS groups into one compact triangulated DFN."""

    if refinement < 1:
        raise SurfaceDfnError("refinement must be positive")
    selected = discover_hgs_groups(directory, variant=variant, groups=groups)
    total = sum(group.element_count for group in selected)
    arrays = {
        "source_nodes": np.empty((total, 3), dtype=np.int32),
        "element_id": np.empty(total, dtype=np.int64),
        "thickness": np.empty(total, dtype=np.float64),
        "conductivity": np.empty(total, dtype=np.float64),
        "porosity": np.empty(total, dtype=np.float64),
        "storage": np.empty(total, dtype=np.float64),
        "group_id": np.empty(total, dtype=np.int32),
    }
    start = 0
    for group in selected:
        end = start + group.element_count
        _read_hgs_group(group, slice(start, end), arrays)
        if validate_pairs:
            _validate_triangle_pairs(
                arrays["source_nodes"][start:end],
                tuple(arrays[name][start:end] for name in ("thickness", "conductivity", "porosity", "storage")),
            )
        start = end

    source_ids, inverse = np.unique(arrays["source_nodes"], return_inverse=True)
    coarse_points, nx, ny, nz = _read_structured_vertices(companion_mesh)
    points = _interpolate_source_nodes(source_ids, coarse_points, nx, ny, nz, refinement)
    return SurfaceDfn(
        points=points,
        triangles=inverse.reshape(-1, 3),
        thickness=arrays["thickness"],
        hydraulic_conductivity=arrays["conductivity"],
        porosity=arrays["porosity"],
        specific_storage=arrays["storage"],
        group_ids=arrays["group_id"],
        fracture_element_ids=arrays["element_id"],
        group_names={group.group_id: group.name for group in selected},
        source_node_ids=source_ids,
        metadata={
            "source_directory": str(Path(directory).resolve()),
            "companion_mesh": str(Path(companion_mesh).resolve()),
            "variant": variant,
            "groups": "physical" if groups == "physical" else list(groups) if groups != "all" else "all",
            "refinement": refinement,
        },
    )


def read_surface_vtk(
    path: str | Path,
    *,
    groups: str | list[str] = "physical",
    active_group_names: list[str] | None = None,
) -> SurfaceDfn:
    """Read a triangle VTK carrying the merged NWMO cell fields."""

    path = Path(path).expanduser().resolve()
    with path.open("rb") as handle:
        header = handle.read(1024)
    is_legacy_polydata = b"DATASET POLYDATA" in header
    if is_legacy_polydata:
        try:
            import vtk
            from vtk.util.numpy_support import vtk_to_numpy
        except ImportError as exc:
            raise SurfaceDfnError("reading legacy VTK POLYDATA requires vtk; install pydelling[cloud]") from exc
        reader = vtk.vtkPolyDataReader()
        reader.SetFileName(str(path))
        reader.Update()
        polydata = reader.GetOutput()
        if polydata.GetNumberOfPoints() == 0 or polydata.GetNumberOfPolys() == 0:
            raise SurfaceDfnError(f"{path}: no polygon data")
        points = vtk_to_numpy(polydata.GetPoints().GetData())
        polygons = polydata.GetPolys()
        offsets_array = polygons.GetOffsetsArray()
        connectivity_array = polygons.GetConnectivityArray()
        if offsets_array is not None and connectivity_array is not None:
            offsets = vtk_to_numpy(offsets_array)
            connectivity = vtk_to_numpy(connectivity_array)
            if np.any(np.diff(offsets) != 3):
                raise SurfaceDfnError(f"{path}: POLYDATA contains non-triangle polygons")
            triangles = connectivity.reshape(-1, 3).astype(np.int64, copy=False)
        else:  # pragma: no cover - compatibility with VTK before cell-array offsets
            packed = vtk_to_numpy(polygons.GetData())
            if len(packed) % 4 or np.any(packed.reshape(-1, 4)[:, 0] != 3):
                raise SurfaceDfnError(f"{path}: POLYDATA contains non-triangle polygons")
            triangles = packed.reshape(-1, 4)[:, 1:].astype(np.int64, copy=False)

        def vtk_arrays(collection):
            arrays = {}
            for index in range(collection.GetNumberOfArrays()):
                array = collection.GetArray(index)
                if array is not None and array.GetName():
                    arrays[array.GetName()] = vtk_to_numpy(array)
            return arrays

        cell_arrays = vtk_arrays(polydata.GetCellData())
        point_arrays = vtk_arrays(polydata.GetPointData())
        field_names = {
            polydata.GetFieldData().GetAbstractArray(index).GetName()
            for index in range(polydata.GetFieldData().GetNumberOfArrays())
            if polydata.GetFieldData().GetAbstractArray(index).GetName()
        }
        blocks = None
        mesh = None
    else:
        mesh = meshio.read(path)
        blocks = [i for i, block in enumerate(mesh.cells) if block.type == "triangle"]
        if not blocks:
            raise SurfaceDfnError(f"{path}: no triangle cells")
        triangles = np.concatenate([mesh.cells[i].data for i in blocks])
        points = mesh.points
        point_arrays = mesh.point_data
        field_names = set(getattr(mesh, "field_data", {}))

    def field(name: str, default=None):
        available = cell_arrays if is_legacy_polydata else mesh.cell_data
        if name not in available:
            if default is None:
                raise SurfaceDfnError(f"{path}: missing cell field {name!r}")
            default_array = np.asarray(default)
            if default_array.shape == (len(triangles),):
                return default_array
            return np.full(len(triangles), default)
        if is_legacy_polydata:
            return np.asarray(available[name])
        return np.concatenate([np.asarray(available[name][i]) for i in blocks])

    group_ids = field("dfn_id", 0).astype(np.int32)
    group_names: dict[int, str] = {}
    for key in field_names:
        match = re.match(r"dfn_id_(\d+)__(.+)", key)
        if match:
            group_names[int(match.group(1))] = match.group(2)
    if not group_names:
        group_names = {int(value): f"group_{int(value)}" for value in np.unique(group_ids)}
    keep = np.ones(len(triangles), dtype=bool)
    if groups == "physical":
        excluded = {
            gid
            for gid, name in group_names.items()
            if name.startswith("SSDFN_FracFace_Set")
        }
        keep &= ~np.isin(group_ids, list(excluded))
    elif groups != "all":
        requested = set(groups)
        available = set(group_names.values())
        missing = requested - available
        if missing:
            raise SurfaceDfnError(f"missing VTK groups: {sorted(missing)}")
        allowed = {gid for gid, name in group_names.items() if name in requested}
        keep &= np.isin(group_ids, list(allowed))
    if active_group_names is not None:
        allowed = {gid for gid, name in group_names.items() if name in set(active_group_names)}
        keep &= np.isin(group_ids, list(allowed))
    ids = np.flatnonzero(keep)
    used, inverse = np.unique(triangles[ids], return_inverse=True)
    return SurfaceDfn(
        points=points[used, :3],
        triangles=inverse.reshape(-1, 3),
        thickness=field("thickness")[ids],
        hydraulic_conductivity=field("hydraulic_conductivity")[ids],
        porosity=field("porosity")[ids],
        specific_storage=field("specific_storage")[ids],
        group_ids=group_ids[ids],
        fracture_element_ids=field("fracture_element_id", np.arange(len(triangles)))[ids],
        group_names=group_names,
        source_node_ids=np.asarray(point_arrays["source_node_id"])[used]
        if "source_node_id" in point_arrays
        else None,
        metadata={
            "source_vtk": str(path),
            "groups": "physical" if groups == "physical" else groups,
        },
    )


#: Public alias for :func:`_read_structured_vertices`, kept so that external
#: consumers do not have to import a private symbol.
read_structured_vertices = _read_structured_vertices
