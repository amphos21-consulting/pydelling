"""Time series of chosen cells and regions, read from PFLOTRAN's HDF5 snapshots."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import h5py
import numpy as np
import pandas as pd

from .base import PostprocessCallback, glob_match
from .geometry import CellGeometry
from .selections import Selection, aggregate

if TYPE_CHECKING:
    from pydelling.managers.pflotran_study import PflotranStudy

COLUMNS = [
    "time_s", "selection", "variable", "unit", "cell", "value", "aggregate", "n_cells", "volume",
]
_NAME_UNIT = re.compile(r"^(?P<variable>.*?)\s*\[(?P<unit>[^\]]*)\]$")


def split_unit(name: str) -> tuple[str, str | None]:
    """``"Total_Tracer_c [M]"`` → ``("Total_Tracer_c", "M")``; no brackets → ``(name, None)``."""
    match = _NAME_UNIT.match(name)
    return (match["variable"], match["unit"]) if match else (name, None)


def _matches(name: str, patterns: Sequence[str]) -> bool:
    bare = split_unit(name)[0]
    return glob_match(name, patterns) or glob_match(bare, patterns)


def snapshot_files(workdir: Path) -> list[Path]:
    """HDF5 files of a run that hold ``Time:`` snapshots, sorted by name."""
    files = []
    for path in sorted(Path(workdir).glob("*.h5")):
        with h5py.File(path, "r") as data:
            if any(key.startswith("Time:") for key in data):
                files.append(path)
    return files


def read_snapshots(
    workdir: Path, variables: Sequence[str], times: Sequence[float] | None = None
) -> tuple[list[tuple[float, Path, str, list[str]]], CellGeometry | None]:
    """Locate the snapshots and variables to extract.

    Args:
        workdir: Folder where PFLOTRAN ran.
        variables: Dataset names or globs.
        times: Seconds to keep (every snapshot if None).

    Returns:
        tuple: ``[(time_s, file, group, datasets), ...]`` sorted by time, and the geometry
        stored in the first file (None for explicit grids).

    Raises:
        ValueError: No snapshot, a time twice, a requested time missing, or no variable.
    """
    from pydelling.managers.batch import time_seconds

    files = snapshot_files(workdir)
    if not files:
        raise ValueError(f"No PFLOTRAN HDF5 snapshots (Time: groups) in {workdir}")
    found: dict[float, tuple[Path, str, list[str]]] = {}
    for path in files:
        with h5py.File(path, "r") as data:
            for key in data:
                if not key.startswith("Time:"):
                    continue
                seconds = time_seconds(key)
                if any(np.isclose(seconds, t, rtol=2e-5, atol=1e-5) for t in found):
                    raise ValueError(f"Snapshot at {seconds} s appears twice ({path.name})")
                names = [name for name in data[key] if _matches(name, variables)]
                found[seconds] = (path, key, names)
    if times is not None:
        kept = {}
        for wanted in times:
            match = [t for t in found if np.isclose(t, wanted, rtol=2e-5, atol=1e-5)]
            if not match:
                raise ValueError(f"No snapshot at {wanted} s; available: {sorted(found)}")
            kept[match[0]] = found[match[0]]
        found = kept
    if not any(names for _, _, names in found.values()):
        raise ValueError(f"No HDF5 variable matches {list(variables)}")
    snapshots = [(t, *found[t]) for t in sorted(found)]
    return snapshots, CellGeometry.from_hdf5(files[0])


class ExtractHDF5(PostprocessCallback):
    """Time series of cells or regions read from the HDF5 snapshots of a PFLOTRAN run.

    Output columns: ``time_s, selection, variable, unit, cell, value, aggregate, n_cells,
    volume``. ``Cell``/``Cells`` give one row per cell (``cell`` set); ``Region``/``Domain``
    one aggregated row (``cell`` empty, ``n_cells``/``volume`` of the group).

    Args:
        variables: Dataset names or globs, with or without unit (``"Total_*"``).
        selections: ``{label: selection}``, e.g.
            ``{"outlet": Cell(x=10.0), "column": Region("all", aggregate="volume_mean")}``.
        times: Seconds to keep; None keeps every snapshot.
        name: Output file stem (``processed/<name>.parquet``).

    Raises:
        ValueError: If there is no selection.

    Example:
        ```python
        template.add_postprocess(ExtractHDF5(
            "Total_*",
            {"outlet": Cell(x=10.0), "mass": Domain("integral")},
        ))
        ```
    """

    def __init__(
        self,
        variables: str | Sequence[str],
        selections: Mapping[str, Selection | dict],
        times: Sequence[float] | None = None,
        name: str = "extractions",
    ) -> None:
        self.variables = [variables] if isinstance(variables, str) else list(variables)
        if not selections:
            raise ValueError("ExtractHDF5 needs at least one selection")
        self.selections = {
            str(label): s if isinstance(s, Selection) else Selection.from_spec(s)
            for label, s in selections.items()
        }
        self.times = None if times is None else [float(t) for t in times]
        self.name = name

    def options(self) -> dict:
        return {
            "variables": self.variables,
            "selections": {label: s.spec() for label, s in self.selections.items()},
            "times": self.times,
            "name": self.name,
        }

    def validate(self, study: PflotranStudy) -> None:
        geometry = CellGeometry.from_deck(study)
        for label, selection in self.selections.items():
            try:
                selection.validate(geometry, study)
            except (ValueError, KeyError, OSError) as exc:
                raise ValueError(f"selection {label!r}: {exc}") from exc

    def process(self, workdir: Path, study: PflotranStudy) -> pd.DataFrame:
        workdir = Path(workdir)
        snapshots, geometry = read_snapshots(workdir, self.variables, self.times)
        if geometry is None:
            geometry = CellGeometry.from_deck(study, workdir)
        cells = {}
        for label, selection in self.selections.items():
            try:
                cells[label] = selection.cells(geometry, study, workdir)
            except (ValueError, KeyError, OSError) as exc:
                raise ValueError(f"selection {label!r}: {exc}") from exc
        volumes = geometry.volumes if geometry is not None else None
        rows = []
        for seconds, path, group, names in snapshots:
            with h5py.File(path, "r") as data:
                for dataset in names:
                    values = data[group][dataset][...]
                    if geometry is not None:
                        values = geometry.natural(values)
                    else:
                        values = values.reshape(-1, order="F" if values.ndim == 3 else "C")
                    variable, unit = split_unit(dataset)
                    for label, selection in self.selections.items():
                        ids = cells[label]
                        if np.any(ids > len(values)):
                            raise ValueError(
                                f"selection {label!r}: cell ids beyond the {len(values)} cells"
                            )
                        chosen = values[ids - 1]
                        cell_volumes = volumes[ids - 1] if volumes is not None else None
                        base = {"time_s": seconds, "selection": label, "variable": variable,
                                "unit": unit}
                        if selection.aggregate is None:
                            for cell, value, volume in zip(
                                ids, chosen,
                                cell_volumes if cell_volumes is not None else [np.nan] * len(ids),
                                strict=True,
                            ):
                                rows.append(base | {"cell": int(cell), "value": float(value),
                                                    "aggregate": None, "n_cells": 1,
                                                    "volume": float(volume)})
                        else:
                            how = selection.aggregate
                            rows.append(base | {
                                "cell": None,
                                "value": aggregate(how, chosen, cell_volumes),
                                "aggregate": how if isinstance(how, str) else how.__name__,
                                "n_cells": len(ids),
                                "volume": float(np.sum(cell_volumes))
                                if cell_volumes is not None else np.nan,
                            })
        frame = pd.DataFrame(rows, columns=COLUMNS)
        frame["cell"] = frame["cell"].astype("Int64")
        return frame
