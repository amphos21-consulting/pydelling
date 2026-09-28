"""PFLOTRAN-specific asset handles.

Kept out of the 3k-line ``handlers.py``. Each handle describes one role of a
detected PFLOTRAN case (see ``pflotran_case.py``) and is selected by
``detect_asset_handle_class`` via the ``pflotran_role`` stamped on nested child
assets. Heavy payloads (the 400 MB ASCII mesh, HDF5 snapshots) are parsed
header-only or via targeted reads so previews stay cheap.
"""

from __future__ import annotations

import re
from functools import cached_property
from pathlib import Path
from typing import Any

import numpy as np

from .handlers import (
    HEADER_READ_BYTES,
    PREVIEW_ROW_LIMIT,
    BaseAssetHandle,
    PflotranMassBalanceAssetHandle,
    PflotranObservationAssetHandle,
)
from .thermodynamic_database import load_thermodynamic_database

# XDMF topology code -> (meshio cell type, node count). PFLOTRAN's explicit
# domain HDF5 encodes cells as ``[code, n0..nk, code, ...]``.
_XDMF_CODE_TO_MESHIO: dict[int, tuple[str, int]] = {
    4: ("triangle", 3),
    5: ("quad", 4),
    6: ("tetra", 4),
    7: ("pyramid", 5),
    8: ("wedge", 6),
    9: ("hexahedron", 8),
}

_TIME_GROUP_RE = re.compile(r"^\s*(\d+)\s+Time\s+(\S+)\s+(\w+)")
# Structured-grid single-file output stores every timestep in one HDF5 file
# with groups named ``Time:  5.18400E+03 s`` (plus ``Coordinates``/``Provenance``).
_SINGLE_FILE_TIME_RE = re.compile(r"^Time:\s*(\S+)\s*(\w*)")
_MOLAR_UNIT_RE = re.compile(r"\[\s*M\s*\]")
_PH_NAME_RE = re.compile(r"(?<![a-z0-9])ph(?![a-z0-9])", re.IGNORECASE)


def _stats_table(title: str, rows: list[list[Any]]) -> dict[str, Any]:
    return {
        "kind": "table",
        "title": title,
        "columns": ["property", "value"],
        "rows": [[str(name), value] for name, value in rows],
    }


def decode_domain_cells(cells: np.ndarray) -> dict[str, np.ndarray]:
    """Decode an XDMF mixed-topology ``Domain/Cells`` array to meshio blocks.

    Fast path for single-element-type meshes (the common case); falls back to a
    Python walk for genuinely mixed topology.
    """
    cells = np.asarray(cells).ravel()
    if cells.size == 0:
        return {}
    first = int(cells[0])
    if first in _XDMF_CODE_TO_MESHIO:
        mtype, node_count = _XDMF_CODE_TO_MESHIO[first]
        stride = node_count + 1
        if cells.size % stride == 0:
            reshaped = cells.reshape(-1, stride)
            if bool(np.all(reshaped[:, 0] == first)):
                return {mtype: reshaped[:, 1:].astype(np.int64)}
    blocks: dict[str, list[np.ndarray]] = {}
    index = 0
    size = cells.size
    while index < size:
        code = int(cells[index])
        spec = _XDMF_CODE_TO_MESHIO.get(code)
        if spec is None:
            break
        mtype, node_count = spec
        connectivity = cells[index + 1 : index + 1 + node_count]
        if connectivity.size < node_count:
            break
        blocks.setdefault(mtype, []).append(connectivity.astype(np.int64))
        index += 1 + node_count
    return {mtype: np.vstack(rows) for mtype, rows in blocks.items()}


class PflotranInputAssetHandle(BaseAssetHandle):
    """Summarize a PFLOTRAN ``.in`` deck (grid, materials, regions, datasets)."""

    kind = "pflotran_input"
    strategy_name = "pflotran_input"

    @cached_property
    def _deck(self) -> dict[str, Any]:
        from pydelling.managers.pflotran_study import PflotranStudy

        text = Path(self.source.path).read_text(errors="ignore")
        grid = re.search(r"(?im)^\s*TYPE\s+(unstructured_\w+|structured\w*)", text)
        sim_type = re.search(r"(?im)^\s*SIMULATION_TYPE\s+(\S+)", text)
        modes = [m.group(1).upper() for m in re.finditer(r"(?im)^\s*MODE\s+(\S+)", text)]
        materials = []
        for match in re.finditer(r"(?is)\bMATERIAL_PROPERTY\s+(\S+)(.*?)\bEND\b", text):
            id_match = re.search(r"(?im)^\s*ID\s+(\d+)", match.group(2))
            materials.append(
                {"name": match.group(1), "id": int(id_match.group(1)) if id_match else None}
            )
        try:
            study = PflotranStudy(str(self.source.path))
            regions = study.get_regions()
        except Exception:
            regions = []
        try:
            final_time = study.get_simulation_time("y")
        except Exception:
            final_time = None
        datasets = re.findall(r"(?im)^\s*DATASET\s+(\S+)\s*$", text)
        return {
            "simulation_type": sim_type.group(1) if sim_type else None,
            "modes": modes,
            "grid_type": grid.group(1).lower() if grid else None,
            "final_time": final_time,
            "final_time_unit": "y",
            "materials": materials,
            "regions": regions,
            "datasets": datasets,
        }

    def schema(self) -> dict[str, Any]:
        deck = self._deck
        return {
            "kind": self.kind,
            "grid_type": deck["grid_type"],
            "n_materials": len(deck["materials"]),
            "n_regions": len(deck["regions"]),
            "n_datasets": len(deck["datasets"]),
            "final_time": deck["final_time"],
        }

    def preview_metadata(self) -> dict[str, Any]:
        return {"pflotran_deck": self._deck}

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        deck = self._deck
        sections: list[dict[str, Any]] = [
            _stats_table(
                "Deck",
                [
                    ["simulation type", deck["simulation_type"]],
                    ["modes", ", ".join(deck["modes"]) or None],
                    ["grid type", deck["grid_type"]],
                    ["final time", f"{deck['final_time']} {deck['final_time_unit']}" if deck["final_time"] is not None else None],
                    ["materials", len(deck["materials"])],
                    ["regions", len(deck["regions"])],
                    ["datasets", len(deck["datasets"])],
                ],
            )
        ]
        if deck["materials"]:
            sections.append(
                {
                    "kind": "table",
                    "title": "Materials",
                    "columns": ["name", "id"],
                    "rows": [[m["name"], m["id"]] for m in deck["materials"][:max_rows]],
                }
            )
        if deck["regions"]:
            sections.append(
                {
                    "kind": "table",
                    "title": "Regions",
                    "columns": ["name"],
                    "rows": [[name] for name in deck["regions"][:max_rows]],
                }
            )
        if deck["datasets"]:
            sections.append(
                {
                    "kind": "table",
                    "title": "Datasets",
                    "columns": ["name"],
                    "rows": [[name] for name in deck["datasets"][:max_rows]],
                }
            )
        return sections

    def to_text(self) -> str:
        return Path(self.source.path).read_text(errors="ignore")

    def summary_text(self) -> str:
        deck = self._deck
        parts = [f"PFLOTRAN deck · {len(deck['materials'])} materials"]
        if deck["final_time"] is not None:
            parts.append(f"final time {deck['final_time']:g} {deck['final_time_unit']}")
        return " · ".join(parts)

    def _flatten_description(self) -> dict[str, Any]:
        return {"pflotran_deck": self._deck}


class PflotranExplicitMeshAssetHandle(BaseAssetHandle):
    """Header-only view of a PFLOTRAN unstructured-explicit ``.mesh`` file.

    Never parses the full (multi-hundred-MB) ASCII body; visualization is served
    by the sibling ``*-domain.h5`` instead.
    """

    kind = "pflotran_mesh"
    strategy_name = "pflotran_mesh"

    @cached_property
    def _header_info(self) -> dict[str, Any]:
        n_cells: int | None = None
        sample: list[list[float]] = []
        with Path(self.source.path).open("r") as handle:
            first = handle.readline().split()
            if len(first) >= 2 and first[0].upper() == "CELLS":
                try:
                    n_cells = int(first[1])
                except ValueError:
                    n_cells = None
            for _ in range(5):
                parts = handle.readline().split()
                if len(parts) >= 4:
                    try:
                        sample.append([float(parts[1]), float(parts[2]), float(parts[3])])
                    except ValueError:
                        break
        bbox = None
        if sample:
            arr = np.array(sample)
            bbox = {"min": arr.min(axis=0).tolist(), "max": arr.max(axis=0).tolist()}
        return {"n_cells": n_cells, "sample_bbox": bbox, "viz_source": "domain_h5"}

    def schema(self) -> dict[str, Any]:
        return {"kind": self.kind, **self._header_info}

    def preview_metadata(self) -> dict[str, Any]:
        return {"pflotran_mesh": self._header_info}

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        info = self._header_info
        return [
            _stats_table(
                "Explicit mesh (header only)",
                [
                    ["cells", info["n_cells"]],
                    ["sampled bbox min", info["sample_bbox"]["min"] if info["sample_bbox"] else None],
                    ["sampled bbox max", info["sample_bbox"]["max"] if info["sample_bbox"] else None],
                    ["visualize via", "sibling domain HDF5"],
                ],
            ),
            {
                "kind": "text",
                "title": "Note",
                "lines": [
                    "This 400 MB-class ASCII mesh is summarized header-only.",
                    "Use the co-located *-domain.h5 asset for 3D visualization.",
                ],
            },
        ]

    def summary_text(self) -> str:
        n_cells = self._header_info["n_cells"]
        return f"Explicit mesh · {n_cells:,} cells (viz via domain HDF5)" if n_cells else "Explicit mesh"


class PflotranGeochemicalDatabaseAssetHandle(BaseAssetHandle):
    """PFLOTRAN thermodynamic database with section-aware metadata."""

    kind = "pflotran_thermodynamic_database"
    strategy_name = "pflotran_thermodynamic_database"

    @cached_property
    def database(self):
        return load_thermodynamic_database(self.source.path)

    def schema(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "temperatures": self.database.temperatures,
            "counts": self.database.counts,
        }

    def preview_metadata(self) -> dict[str, Any]:
        return {"thermodynamic_database": self.schema()}

    def preview_sections(
        self,
        *,
        max_rows: int = PREVIEW_ROW_LIMIT,
        max_bytes: int = HEADER_READ_BYTES,
    ) -> list[dict[str, Any]]:
        del max_rows, max_bytes
        return [
            {
                "kind": "thermodynamic_database",
                "title": "Thermodynamic database",
                "metadata": {
                    "temperatures": self.database.temperatures,
                    "counts": self.database.counts,
                    "warnings": self.database.warnings[:20],
                },
            }
        ]

    def summary_text(self) -> str:
        total = sum(self.database.counts.values())
        return (
            f"Thermodynamic database · {total:,} species · "
            f"{len(self.database.temperatures)} temperatures"
        )


class PflotranDomainAssetHandle(BaseAssetHandle):
    """PFLOTRAN explicit domain HDF5 (``/Domain/Cells`` + ``/Domain/Vertices``).

    This is the mesh visualization source: ``to_vtk`` reconstructs the volume mesh.
    """

    kind = "pflotran_domain"
    strategy_name = "pflotran_domain"

    @cached_property
    def _domain_info(self) -> dict[str, Any]:
        import h5py

        with h5py.File(self.source.path, "r") as handle:
            n_vertices = int(handle["Domain/Vertices"].shape[0])
            cells = handle["Domain/Cells"][:]
        blocks = decode_domain_cells(cells)
        cell_types = {mtype: int(conn.shape[0]) for mtype, conn in blocks.items()}
        return {
            "n_vertices": n_vertices,
            "n_cells": int(sum(cell_types.values())),
            "cell_types": cell_types,
        }

    def schema(self) -> dict[str, Any]:
        return {"kind": self.kind, **self._domain_info}

    def preview_metadata(self) -> dict[str, Any]:
        return {"pflotran_domain": self._domain_info}

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        info = self._domain_info
        rows = [["vertices", info["n_vertices"]], ["cells", info["n_cells"]]]
        rows.extend([[f"cells · {mtype}", count] for mtype, count in info["cell_types"].items()])
        return [_stats_table("Domain mesh", rows)]

    def to_vtk(self, filename: str | Path):
        import h5py
        import meshio

        with h5py.File(self.source.path, "r") as handle:
            vertices = np.asarray(handle["Domain/Vertices"][:], dtype=float)
            cells = handle["Domain/Cells"][:]
        blocks = decode_domain_cells(cells)
        mesh = meshio.Mesh(
            points=vertices,
            cells=[(mtype, conn) for mtype, conn in blocks.items()],
        )
        mesh.write(str(filename))
        return filename

    def summary_text(self) -> str:
        info = self._domain_info
        return f"Domain mesh · {info['n_cells']:,} cells · {info['n_vertices']:,} vertices"


class PflotranBcDatasetAssetHandle(BaseAssetHandle):
    """PFLOTRAN boundary-condition dataset HDF5 (``Data`` + ``Times`` groups)."""

    kind = "pflotran_bc_dataset"
    strategy_name = "pflotran_bc_dataset"

    @cached_property
    def _dataset_info(self) -> dict[str, Any]:
        import h5py

        with h5py.File(self.source.path, "r") as handle:
            group_name, data, times = None, None, None
            for name, obj in handle.items():
                if isinstance(obj, h5py.Group) and "Data" in obj:
                    group_name = name
                    data = obj["Data"][:]
                    times = obj["Times"][()] if "Times" in obj else None
                    break
            if data is None and "Data" in handle:
                group_name = ""
                data = handle["Data"][:]
                times = handle["Times"][()] if "Times" in handle else None
        if data is None:
            return {"group": None, "data_shape": None, "n_times": 0, "times": []}
        times_list = np.atleast_1d(np.asarray(times)).astype(float).tolist() if times is not None else []
        # Downsample the first time slice to a small heatmap grid.
        slice2d = np.asarray(data)
        while slice2d.ndim > 2:
            slice2d = slice2d[..., 0] if slice2d.shape[-1] == 1 else slice2d[..., 0]
        heatmap = None
        if slice2d.ndim == 2 and slice2d.size:
            step_r = max(1, slice2d.shape[0] // 200)
            step_c = max(1, slice2d.shape[1] // 200)
            heatmap = slice2d[::step_r, ::step_c].astype(float).tolist()
        arr = np.asarray(data, dtype=float)
        return {
            "group": group_name,
            "data_shape": list(np.asarray(data).shape),
            "n_times": len(times_list),
            "times": times_list,
            "data_min": float(arr.min()) if arr.size else None,
            "data_max": float(arr.max()) if arr.size else None,
            "data_mean": float(arr.mean()) if arr.size else None,
            "heatmap": heatmap,
        }

    def schema(self) -> dict[str, Any]:
        info = self._dataset_info
        return {
            "kind": self.kind,
            "group": info["group"],
            "data_shape": info["data_shape"],
            "n_times": info["n_times"],
        }

    def read_heatmap(self, time_index: int = 0) -> dict[str, Any]:
        """Return one bounded 2D slice for interactive preview."""
        import h5py

        with h5py.File(self.source.path, "r") as handle:
            group = next(
                (
                    value
                    for value in handle.values()
                    if isinstance(value, h5py.Group) and "Data" in value
                ),
                handle,
            )
            data = np.asarray(group["Data"][()])
            times = (
                np.atleast_1d(np.asarray(group["Times"][()])).astype(float)
                if "Times" in group
                else np.empty(0, dtype=float)
            )
        if time_index < 0 or (times.size and time_index >= times.size):
            raise IndexError(
                f"time_index {time_index} out of range "
                f"(0..{max(int(times.size) - 1, 0)})"
            )
        selected = data
        if times.size and data.ndim:
            if data.shape[-1] == times.size:
                selected = np.take(data, time_index, axis=-1)
            elif data.shape[0] == times.size:
                selected = np.take(data, time_index, axis=0)
        selected = np.squeeze(selected)
        while selected.ndim > 2:
            selected = selected[..., 0]
        if selected.ndim == 1:
            selected = selected.reshape(1, -1)
        step_r = max(1, selected.shape[0] // 250) if selected.ndim == 2 else 1
        step_c = max(1, selected.shape[1] // 250) if selected.ndim == 2 else 1
        return {
            "time_index": time_index,
            "time": float(times[time_index]) if times.size else None,
            "times": times.tolist(),
            "shape": list(data.shape),
            "z": selected[::step_r, ::step_c].astype(float).tolist()
            if selected.ndim == 2
            else [],
        }

    def preview_metadata(self) -> dict[str, Any]:
        return {"pflotran_bc_dataset": {k: v for k, v in self._dataset_info.items() if k != "heatmap"}}

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        info = self._dataset_info
        sections: list[dict[str, Any]] = [
            _stats_table(
                "Boundary dataset",
                [
                    ["group", info["group"]],
                    ["data shape", info["data_shape"]],
                    ["times", info["n_times"]],
                    ["min", info["data_min"]],
                    ["max", info["data_max"]],
                    ["mean", info["data_mean"]],
                ],
            )
        ]
        if info["heatmap"] is not None:
            sections.append(
                {
                    "kind": "heatmap",
                    "title": "Data (downsampled)",
                    "metadata": {"z": info["heatmap"]},
                }
            )
        return sections

    def summary_text(self) -> str:
        info = self._dataset_info
        shape = "×".join(str(d) for d in info["data_shape"]) if info["data_shape"] else "?"
        return f"BC dataset · {shape} · {info['n_times']} time(s)"


class MaterialIdsAssetHandle(BaseAssetHandle):
    """PFLOTRAN ``.mat`` material file (a cell-id list)."""

    kind = "pflotran_material_ids"
    strategy_name = "pflotran_material_ids"

    @cached_property
    def _info(self) -> dict[str, Any]:
        from pydelling.readers.iGPReader.io import read_material_ids

        summary = read_material_ids(self.source.path)
        ids = summary.pop("ids")
        summary["sample"] = ids[:PREVIEW_ROW_LIMIT].tolist() if ids.size else []
        return summary

    def schema(self) -> dict[str, Any]:
        return {"kind": self.kind, **{k: v for k, v in self._info.items() if k != "sample"}}

    def preview_metadata(self) -> dict[str, Any]:
        return {"pflotran_material_ids": {k: v for k, v in self._info.items() if k != "sample"}}

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        info = self._info
        return [
            _stats_table(
                "Material region",
                [["cells", info["count"]], ["min cell id", info["min"]], ["max cell id", info["max"]]],
            )
        ]

    def summary_text(self) -> str:
        return f"Material region · {self._info['count']:,} cells"


class ExplicitBoundaryAssetHandle(BaseAssetHandle):
    """PFLOTRAN ``.ex`` explicit boundary connection file."""

    kind = "pflotran_boundary"
    strategy_name = "pflotran_boundary"

    @cached_property
    def _info(self) -> dict[str, Any]:
        from pydelling.readers.iGPReader.io import read_boundary_connections

        summary = read_boundary_connections(self.source.path)
        summary.pop("element_ids", None)
        summary.pop("centroids", None)
        summary.pop("areas", None)
        return summary

    def schema(self) -> dict[str, Any]:
        return {"kind": self.kind, **self._info}

    def preview_metadata(self) -> dict[str, Any]:
        return {"pflotran_boundary": self._info}

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        info = self._info
        return [
            _stats_table(
                "Boundary connections",
                [
                    ["declared faces", info["declared_count"]],
                    ["faces", info["face_count"]],
                    ["total area", info["total_area"]],
                    ["area min", info["area_min"]],
                    ["area max", info["area_max"]],
                ],
            )
        ]

    def summary_text(self) -> str:
        info = self._info
        return f"Boundary · {info['face_count']:,} faces · area {info['total_area']:.3g}"


class PflotranResultsAssetHandle(BaseAssetHandle):
    """Unified multi-timestep PFLOTRAN results (snapshot HDF5 files).

    Enumerates snapshot files (from ``metadata['pflotran_results']`` when present,
    otherwise by globbing the co-located directory) to expose times + variables.
    """

    kind = "pflotran_results"
    strategy_name = "pflotran_results"

    @staticmethod
    def _default_variable(variables: list[str]) -> str | None:
        """Choose the most useful field to show when no variable is requested."""
        preferences = (
            lambda name: "concentration" in name.lower(),
            lambda name: "tracer" in name.lower(),
            lambda name: bool(_MOLAR_UNIT_RE.search(name)),
            lambda name: bool(_PH_NAME_RE.search(name)),
        )
        for matches in preferences:
            preferred = next((name for name in variables if matches(name)), None)
            if preferred is not None:
                return preferred
        return variables[0] if variables else None

    def _base_dir(self) -> Path:
        base = Path(self.source.path)
        return base if base.is_dir() else base.parent

    def _snapshot_paths(self) -> list[Path]:
        metadata = self.source.metadata or {}
        results = metadata.get("pflotran_results") or {}
        base = Path(self.source.path)
        base_dir = self._base_dir()
        timesteps = results.get("timesteps")
        if isinstance(timesteps, list) and timesteps:
            paths = []
            for step in timesteps:
                rel = step.get("file") if isinstance(step, dict) else None
                if rel:
                    paths.append(base_dir / rel)
            if paths:
                return paths
        stem = results.get("stem") or base.stem
        match = re.match(r"^(.*)-\d{3}$", stem)
        if match:
            stem = match.group(1)
        globbed = sorted(base_dir.glob(f"{stem}-[0-9][0-9][0-9].h5"))
        if globbed:
            return globbed
        # Structured-grid runs write a single ``{stem}.h5`` holding every
        # timestep; fall back to the file itself.
        if base.is_file():
            return [base]
        single = base_dir / f"{stem}.h5"
        return [single] if single.is_file() else []

    @staticmethod
    def _match_time_group(group_name: str) -> tuple[float | None, str | None] | None:
        """Parse a time group name in either PFLOTRAN output layout, or ``None``."""
        match = _TIME_GROUP_RE.match(group_name)
        if match:
            try:
                time_value = float(match.group(2))
            except ValueError:
                time_value = None
            return time_value, match.group(3)
        single = _SINGLE_FILE_TIME_RE.match(group_name)
        if single:
            try:
                time_value = float(single.group(1))
            except ValueError:
                time_value = None
            return time_value, single.group(2) or None
        return None

    @cached_property
    def _results_info(self) -> dict[str, Any]:
        import h5py

        paths = self._snapshot_paths()
        timesteps: list[dict[str, Any]] = []
        variables: list[str] = []
        skipped: list[dict[str, str]] = []
        for path in paths:
            if not path.exists():
                skipped.append({"file": path.name, "error": "file not found"})
                continue
            file_steps: list[dict[str, Any]] = []
            try:
                with h5py.File(path, "r") as handle:
                    for group_name, obj in handle.items():
                        if not isinstance(obj, h5py.Group):
                            continue
                        parsed = self._match_time_group(group_name)
                        if parsed is None:
                            continue
                        time_value, time_unit = parsed
                        file_steps.append(
                            {
                                "file": path.name,
                                "group": group_name,
                                "time": time_value,
                                "time_unit": time_unit,
                            }
                        )
                        if not variables:
                            variables = list(obj.keys())
                    if not file_steps:
                        # Legacy fallback: treat the first non-auxiliary group
                        # as a single unnamed timestep.
                        group_name = next(
                            (
                                key
                                for key, value in handle.items()
                                if isinstance(value, h5py.Group)
                                and key not in {"Coordinates", "Provenance"}
                            ),
                            None,
                        )
                        if group_name is not None:
                            file_steps.append(
                                {
                                    "file": path.name,
                                    "group": group_name,
                                    "time": None,
                                    "time_unit": None,
                                }
                            )
                            if not variables:
                                variables = list(handle[group_name].keys())
            except OSError as exc:
                skipped.append({"file": path.name, "error": str(exc)})
                continue
            # h5py iterates groups alphabetically, which misorders exponent
            # notation ("5.18400E+03" < "8.64000E+02"); order by parsed time.
            file_steps.sort(key=lambda step: (step["time"] is None, step["time"] or 0.0))
            timesteps.extend(file_steps)
        for index, step in enumerate(timesteps):
            step["index"] = index
        return {
            "timesteps": timesteps,
            "n_timesteps": len(timesteps),
            "variables": variables,
            "times": [t["time"] for t in timesteps],
            "skipped": skipped,
        }

    @property
    def results_info(self) -> dict[str, Any]:
        """Public accessor for enumerated timesteps + variables."""
        return self._results_info

    def _coordinates_from(self, paths: list[Path]) -> dict[str, np.ndarray] | None:
        """Return structured cell-edge coordinates from the first file that has them.

        PFLOTRAN structured HDF5 output stores a ``Coordinates`` group with
        ``X [m]``/``Y [m]``/``Z [m]`` edge arrays (one file, or the first
        snapshot in per-file mode). Returns ``None`` for unstructured output.
        """
        import h5py

        for path in paths:
            if not Path(path).exists():
                continue
            try:
                with h5py.File(path, "r") as handle:
                    if "Coordinates" not in handle:
                        continue
                    group = handle["Coordinates"]
                    axes = list(group.keys())
                    if len(axes) < 3:
                        continue
                    return {
                        "x": np.asarray(group[axes[0]][()], dtype=float),
                        "y": np.asarray(group[axes[1]][()], dtype=float),
                        "z": np.asarray(group[axes[2]][()], dtype=float),
                    }
            except OSError:
                continue
        return None

    def read_field(
        self, time_index: int, variable: str | None = None
    ) -> dict[str, Any]:
        """Read one variable at one timestep, plus structured coordinates.

        Returns ``{"variable", "values", "coordinates", "time", "time_unit"}``.
        ``coordinates`` is ``None`` when the results are unstructured.
        """
        import h5py

        info = self._results_info
        steps = info["timesteps"]
        if not steps:
            raise ValueError("No PFLOTRAN result timesteps available.")
        if not 0 <= time_index < len(steps):
            raise IndexError(
                f"time_index {time_index} out of range (0..{len(steps) - 1})"
            )
        variables = info["variables"]
        if variable is None:
            variable = self._default_variable(variables)
        if variable is None:
            raise ValueError("No variables available in PFLOTRAN results.")
        if variable not in variables:
            raise KeyError(
                f"Unknown variable {variable!r}; available: {variables}"
            )

        step = steps[time_index]
        path = self._base_dir() / step["file"]
        with h5py.File(path, "r") as handle:
            group = handle.get(step.get("group") or "")
            if group is None:
                group_name = next(
                    (
                        key
                        for key in handle.keys()
                        if self._match_time_group(key) is not None
                    ),
                    None,
                )
                group = handle.get(group_name) if group_name else None
            if group is None or variable not in group:
                raise KeyError(
                    f"Variable {variable!r} not found in snapshot {path.name}."
                )
            values = np.asarray(group[variable][()], dtype=float).ravel()
        coordinates = self._coordinates_from(self._snapshot_paths())
        return {
            "variable": variable,
            "values": values,
            "coordinates": coordinates,
            "time": step["time"],
            "time_unit": step["time_unit"],
        }

    def schema(self) -> dict[str, Any]:
        info = self._results_info
        return {
            "kind": self.kind,
            "n_timesteps": info["n_timesteps"],
            "variables": info["variables"],
        }

    def preview_metadata(self) -> dict[str, Any]:
        return {"pflotran_results": self._results_info}

    def preview_warnings(self) -> list[str]:
        """Return warnings for snapshots that could not be read.

        Category: asset-handle
        Tags: pflotran, results, warnings, preview
        Usage: preview documents must surface unreadable snapshot files instead of dropping them silently.

        Returns:
            list[str]: one message per skipped snapshot file.
        """
        return [
            f"Skipped unreadable snapshot {item['file']}: {item['error']}"
            for item in self._results_info["skipped"]
        ]

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        info = self._results_info
        stats_rows = [["timesteps", info["n_timesteps"]], ["variables", len(info["variables"])]]
        if info["skipped"]:
            stats_rows.append(["skipped snapshots", len(info["skipped"])])
        sections: list[dict[str, Any]] = [_stats_table("Results", stats_rows)]
        if info["timesteps"]:
            sections.append(
                {
                    "kind": "table",
                    "title": "Timesteps",
                    "columns": ["index", "file", "time", "unit"],
                    "rows": [
                        [t["index"], t["file"], t["time"], t["time_unit"]]
                        for t in info["timesteps"][:max_rows]
                    ],
                }
            )
        if info["skipped"]:
            sections.append(
                {
                    "kind": "text",
                    "title": "Warnings",
                    "lines": self.preview_warnings()[:10],
                }
            )
        return sections

    def summary_text(self) -> str:
        info = self._results_info
        summary = f"PFLOTRAN results · {info['n_timesteps']} timesteps · {len(info['variables'])} variables"
        if info["skipped"]:
            summary += f" · {len(info['skipped'])} unreadable"
        return summary


class PflotranXdmfAssetHandle(BaseAssetHandle):
    """PFLOTRAN XDMF sidecar (``.xmf``): light XML index over snapshot HDF5 files.

    Category: asset-handle
    Tags: pflotran, xdmf, xmf, snapshot, hdf5, references
    Usage: the asset is a per-timestep XDMF descriptor and scripts need its grid, time, variables, and referenced HDF5 files.
    """

    kind = "pflotran_xdmf"
    strategy_name = "pflotran_xdmf"

    @cached_property
    def _xdmf_info(self) -> dict[str, Any]:
        import xml.etree.ElementTree as ET

        info: dict[str, Any] = {
            "grid_name": None,
            "time": None,
            "time_unit": None,
            "topology_type": None,
            "n_cells": None,
            "geometry_type": None,
            "attributes": [],
            "h5_references": [],
            "snapshot_file": None,
            "domain_file": None,
            "warnings": [],
        }
        try:
            root = ET.parse(self.source.path).getroot()
        except (ET.ParseError, OSError) as exc:
            info["warnings"].append(f"Could not parse XDMF: {exc}")
            return info
        grid = next(iter(root.iter("Grid")), None)
        if grid is None:
            info["warnings"].append("No <Grid> element found in the XDMF document.")
            return info
        info["grid_name"] = grid.get("Name")
        time_el = grid.find("Time")
        if time_el is not None:
            try:
                info["time"] = float(time_el.get("Value"))
            except (TypeError, ValueError):
                pass
        topology = grid.find("Topology")
        if topology is not None:
            info["topology_type"] = topology.get("Type") or topology.get("TopologyType")
            try:
                info["n_cells"] = int(topology.get("NumberOfElements"))
            except (TypeError, ValueError):
                pass
        geometry = grid.find("Geometry")
        if geometry is not None:
            info["geometry_type"] = geometry.get("GeometryType") or geometry.get("Type")
        info["attributes"] = [
            {
                "name": attribute.get("Name"),
                "type": attribute.get("AttributeType"),
                "center": attribute.get("Center"),
            }
            for attribute in grid.findall("Attribute")
        ]
        references: dict[str, list[str]] = {}
        for item in root.iter("DataItem"):
            if (item.get("Format") or "").upper() != "HDF":
                continue
            text = (item.text or "").strip()
            file_part, separator, dataset = text.partition(":")
            if not separator:
                continue
            references.setdefault(file_part.strip(), []).append(dataset.strip())
        info["h5_references"] = [
            {"file": name, "datasets": sorted(set(datasets))}
            for name, datasets in sorted(references.items())
        ]
        for name, datasets in references.items():
            if any(dataset.lstrip("/").startswith("Domain") for dataset in datasets):
                info["domain_file"] = name
                continue
            if info["snapshot_file"] is None:
                info["snapshot_file"] = name
            if info["time_unit"] is None:
                for dataset in datasets:
                    match = _TIME_GROUP_RE.match(dataset.lstrip("/"))
                    if match:
                        info["time_unit"] = match.group(3)
                        break
        return info

    def schema(self) -> dict[str, Any]:
        """Return XDMF grid and reference metadata.

        Category: asset-handle
        Tags: pflotran, xdmf, schema, grid, references
        Usage: scripts need cell counts, time, and referenced HDF5 files without opening heavy data.

        Returns:
            dict[str, Any]: XDMF schema metadata.
        """
        info = self._xdmf_info
        return {
            "kind": self.kind,
            "grid_name": info["grid_name"],
            "n_cells": info["n_cells"],
            "time": info["time"],
            "time_unit": info["time_unit"],
            "topology_type": info["topology_type"],
            "geometry_type": info["geometry_type"],
            "n_attributes": len(info["attributes"]),
            "snapshot_file": info["snapshot_file"],
            "domain_file": info["domain_file"],
        }

    def preview_metadata(self) -> dict[str, Any]:
        return {"pflotran_xdmf": self._xdmf_info}

    def preview_warnings(self) -> list[str]:
        return list(self._xdmf_info["warnings"])

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        info = self._xdmf_info
        time_label = None
        if info["time"] is not None:
            time_label = f"{info['time']:g}" + (f" {info['time_unit']}" if info["time_unit"] else "")
        sections: list[dict[str, Any]] = [
            _stats_table(
                "XDMF snapshot",
                [
                    ["grid", info["grid_name"]],
                    ["time", time_label],
                    ["topology", info["topology_type"]],
                    ["cells", info["n_cells"]],
                    ["geometry", info["geometry_type"]],
                    ["snapshot HDF5", info["snapshot_file"]],
                    ["domain HDF5", info["domain_file"]],
                ],
            )
        ]
        if info["attributes"]:
            sections.append(
                {
                    "kind": "table",
                    "title": "Attributes",
                    "columns": ["name", "type", "center"],
                    "rows": [
                        [attribute["name"], attribute["type"], attribute["center"]]
                        for attribute in info["attributes"][:max_rows]
                    ],
                }
            )
        if info["h5_references"]:
            sections.append(
                {
                    "kind": "table",
                    "title": "HDF5 references",
                    "columns": ["file", "datasets"],
                    "rows": [
                        [reference["file"], len(reference["datasets"])]
                        for reference in info["h5_references"][:max_rows]
                    ],
                }
            )
        if info["warnings"]:
            sections.append(
                {"kind": "text", "title": "Warnings", "lines": info["warnings"][:10]}
            )
        return sections

    def to_text(self) -> str:
        """Load the raw XDMF XML text.

        Category: asset-handle
        Tags: pflotran, xdmf, text, xml
        Usage: scripts need the raw XDMF document, e.g. to rewrite references.

        Returns:
            str: XDMF document text.
        """
        return Path(self.source.path).read_text(errors="ignore")

    def summary_text(self) -> str:
        info = self._xdmf_info
        parts = ["XDMF snapshot"]
        if info["time"] is not None:
            unit = f" {info['time_unit']}" if info["time_unit"] else ""
            parts.append(f"t={info['time']:g}{unit}")
        if info["n_cells"] is not None:
            parts.append(f"{info['n_cells']:,} cells")
        if info["attributes"]:
            parts.append(f"{len(info['attributes'])} variables")
        return " · ".join(parts)

    def _flatten_description(self) -> dict[str, Any]:
        info = self._xdmf_info
        return {
            "xdmf": {
                "time": info["time"],
                "time_unit": info["time_unit"],
                "n_cells": info["n_cells"],
                "attributes": [attribute["name"] for attribute in info["attributes"]],
                "snapshot_file": info["snapshot_file"],
                "domain_file": info["domain_file"],
            }
        }


_SECONDS_PER_YEAR = 3.15576e7


class PflotranRestartAssetHandle(BaseAssetHandle):
    """PFLOTRAN restart checkpoint HDF5 (``/Checkpoint`` tree).

    Category: asset-handle
    Tags: pflotran, restart, checkpoint, hdf5, timestepper
    Usage: the asset is a PFLOTRAN restart file and scripts need checkpoint time, step counts, or stored variables.
    """

    kind = "pflotran_restart"
    strategy_name = "pflotran_restart"

    _TIMESTEPPER_FIELDS = (
        ("Time", "time"),
        ("Dt", "dt"),
        ("Prev_dt", "prev_dt"),
        ("Num_steps", "num_steps"),
        ("Cumulative_newton_iterations", "newton_iterations"),
        ("Cumulative_linear_iterations", "linear_iterations"),
        ("Cumulative_time_step_cuts", "time_step_cuts"),
    )

    @staticmethod
    def _scalar(dataset: Any) -> float | int | None:
        try:
            value = np.atleast_1d(np.asarray(dataset[()])).ravel()[0]
        except (IndexError, TypeError, ValueError):
            return None
        if isinstance(value, (np.integer, int)):
            return int(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @cached_property
    def _checkpoint_info(self) -> dict[str, Any]:
        import h5py

        info: dict[str, Any] = {
            "revision": None,
            "process_models": [],
            "datasets": [],
            "datasets_truncated": False,
            "warnings": [],
        }
        datasets: list[dict[str, Any]] = []

        def collect(name: str, obj: Any) -> None:
            if isinstance(obj, h5py.Dataset) and len(datasets) < 50:
                datasets.append(
                    {"name": name, "shape": list(obj.shape), "dtype": str(obj.dtype)}
                )
            elif isinstance(obj, h5py.Dataset):
                info["datasets_truncated"] = True

        try:
            with h5py.File(self.source.path, "r") as handle:
                handle.visititems(collect)
                info["datasets"] = datasets
                checkpoint = handle.get("Checkpoint")
                if not isinstance(checkpoint, h5py.Group):
                    info["warnings"].append(
                        "No /Checkpoint group: this HDF5 file does not look like a "
                        "PFLOTRAN restart checkpoint."
                    )
                    return info
                revision = checkpoint.get("Revision Number")
                if isinstance(revision, h5py.Dataset):
                    info["revision"] = self._scalar(revision)
                for name, group in checkpoint.items():
                    if not isinstance(group, h5py.Group):
                        continue
                    entry: dict[str, Any] = {"name": name}
                    timestepper = group.get("Timestepper")
                    if isinstance(timestepper, h5py.Group):
                        for dataset_name, field in self._TIMESTEPPER_FIELDS:
                            dataset = timestepper.get(dataset_name)
                            entry[field] = (
                                self._scalar(dataset)
                                if isinstance(dataset, h5py.Dataset)
                                else None
                            )
                    variables: list[dict[str, Any]] = []
                    for sub_name, sub_group in group.items():
                        if sub_name == "Timestepper" or not isinstance(sub_group, h5py.Group):
                            continue
                        for variable_name, dataset in sub_group.items():
                            if isinstance(dataset, h5py.Dataset):
                                variables.append(
                                    {
                                        "name": f"{sub_name}/{variable_name}",
                                        "shape": list(dataset.shape),
                                        "dtype": str(dataset.dtype),
                                    }
                                )
                    entry["variables"] = variables[:50]
                    entry["n_variables"] = len(variables)
                    info["process_models"].append(entry)
        except OSError as exc:
            info["warnings"].append(f"Could not read HDF5 file: {exc}")
        return info

    def schema(self) -> dict[str, Any]:
        """Return checkpoint metadata for this restart file.

        Category: asset-handle
        Tags: pflotran, restart, schema, checkpoint
        Usage: scripts need checkpoint time, revision, and process-model overview.

        Returns:
            dict[str, Any]: restart checkpoint schema metadata.
        """
        info = self._checkpoint_info
        first = info["process_models"][0] if info["process_models"] else {}
        return {
            "kind": self.kind,
            "revision": info["revision"],
            "n_process_models": len(info["process_models"]),
            "process_models": [entry["name"] for entry in info["process_models"]],
            "time_seconds": first.get("time"),
            "n_datasets": len(info["datasets"]),
        }

    def preview_metadata(self) -> dict[str, Any]:
        info = self._checkpoint_info
        return {
            "pflotran_restart": {
                "revision": info["revision"],
                "process_models": [
                    {key: value for key, value in entry.items() if key != "variables"}
                    for entry in info["process_models"]
                ],
            }
        }

    def preview_warnings(self) -> list[str]:
        return list(self._checkpoint_info["warnings"])

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        info = self._checkpoint_info
        rows: list[list[Any]] = [
            ["revision", info["revision"]],
            ["process models", len(info["process_models"])],
        ]
        for entry in info["process_models"]:
            name = entry["name"]
            time_seconds = entry.get("time")
            if time_seconds is not None:
                rows.append([f"{name} · time [s]", f"{time_seconds:.6g}"])
                rows.append(
                    [f"{name} · time [y] (approx.)", f"{time_seconds / _SECONDS_PER_YEAR:.6g}"]
                )
            if entry.get("dt") is not None:
                rows.append([f"{name} · dt [s]", f"{entry['dt']:.6g}"])
            if entry.get("num_steps") is not None:
                rows.append([f"{name} · steps", entry["num_steps"]])
            if entry.get("newton_iterations") is not None:
                rows.append([f"{name} · newton iterations", entry["newton_iterations"]])
            if entry.get("linear_iterations") is not None:
                rows.append([f"{name} · linear iterations", entry["linear_iterations"]])
            if entry.get("time_step_cuts") is not None:
                rows.append([f"{name} · time-step cuts", entry["time_step_cuts"]])
            rows.append([f"{name} · stored variables", entry.get("n_variables")])
        sections: list[dict[str, Any]] = [_stats_table("Checkpoint", rows)]
        if info["datasets"]:
            sections.append(
                {
                    "kind": "hdf5",
                    "title": "Datasets",
                    "datasets": info["datasets"],
                    "truncated": info["datasets_truncated"],
                }
            )
        if info["warnings"]:
            sections.append(
                {"kind": "text", "title": "Warnings", "lines": info["warnings"][:10]}
            )
        return sections

    def summary_text(self) -> str:
        info = self._checkpoint_info
        if not info["process_models"]:
            return "Restart checkpoint (unrecognized layout)"
        first = info["process_models"][0]
        time_seconds = first.get("time")
        time_label = f" · t={time_seconds:.4g} s" if time_seconds is not None else ""
        return (
            f"Restart checkpoint{time_label} · "
            f"{len(info['process_models'])} process model(s)"
        )

    def _flatten_description(self) -> dict[str, Any]:
        info = self._checkpoint_info
        return {
            "pflotran_restart": {
                "revision": info["revision"],
                "process_models": [
                    {
                        "name": entry["name"],
                        "time": entry.get("time"),
                        "num_steps": entry.get("num_steps"),
                        "n_variables": entry.get("n_variables"),
                    }
                    for entry in info["process_models"]
                ],
            }
        }


_PFLOTRAN_ROLE_HANDLES: dict[str, type[BaseAssetHandle]] = {
    "input_file": PflotranInputAssetHandle,
    "mesh": PflotranExplicitMeshAssetHandle,
    "domain_h5": PflotranDomainAssetHandle,
    "bc_dataset_h5": PflotranBcDatasetAssetHandle,
    "material_ids": MaterialIdsAssetHandle,
    "boundary_ex": ExplicitBoundaryAssetHandle,
    "mass_balance": PflotranMassBalanceAssetHandle,
    "geochem_db": PflotranGeochemicalDatabaseAssetHandle,
    "output_snapshot": PflotranResultsAssetHandle,
    "pflotran_results": PflotranResultsAssetHandle,
    "output_xmf": PflotranXdmfAssetHandle,
    "restart": PflotranRestartAssetHandle,
    "observation": PflotranObservationAssetHandle,
}


def pflotran_handle_for_role(
    role: str | None, metadata: dict[str, Any] | None
) -> type[BaseAssetHandle] | None:
    """Return the specialized handle class for a PFLOTRAN role, or ``None``.

    Used by ``detect_asset_handle_class`` to route nested children stamped with a
    ``pflotran_role`` (and results assets marked ``asset_kind='pflotran_results'``)
    before falling back to content sniffing.
    """
    metadata = metadata or {}
    if metadata.get("asset_kind") == "pflotran_results":
        return PflotranResultsAssetHandle
    if role:
        return _PFLOTRAN_ROLE_HANDLES.get(role)
    return None


__all__ = [
    "PflotranInputAssetHandle",
    "PflotranExplicitMeshAssetHandle",
    "PflotranDomainAssetHandle",
    "PflotranBcDatasetAssetHandle",
    "MaterialIdsAssetHandle",
    "ExplicitBoundaryAssetHandle",
    "PflotranResultsAssetHandle",
    "PflotranGeochemicalDatabaseAssetHandle",
    "PflotranRestartAssetHandle",
    "PflotranXdmfAssetHandle",
    "decode_domain_cells",
    "pflotran_handle_for_role",
]
