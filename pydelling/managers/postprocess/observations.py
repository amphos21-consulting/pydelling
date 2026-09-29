"""PFLOTRAN observation points (``OBSERVATION`` cards) as one long table.

PFLOTRAN writes one ``<prefix>-obs-<rank>.pft`` file per MPI rank that owns observation
cells. The first header column is ``"Time [<unit>]"``, then one column per variable and
observed cell: ``"<variable> [<unit>] <region> (<cell id>) (<x> <y> <z>)"``.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from .base import PostprocessCallback, glob_match

if TYPE_CHECKING:
    from pydelling.managers.pflotran_study import PflotranStudy

COLUMNS = ["time_s", "point", "cell", "x", "y", "z", "variable", "unit", "value"]
OBSERVATION_FILES = ("*-obs-*.pft", "*-obs-*.tec")
_HEADER = re.compile(
    r"^(?:\d+-)?(?P<variable>.+?)(?:\s*\[(?P<unit>[^\]]*)\])?"
    r"\s+(?P<point>\S+)\s+\((?P<cell>\d+)\)\s+\((?P<coordinates>[^)]*)\)$"
)
_FORTRAN_EXPONENT = re.compile(r"(?<=\d)([+-]\d{3})$")  # 1.0-100 is 1.0E-100


def fortran_float(token: str) -> float:
    """Parse a Fortran real: ``1.5d0``, ``2.D-3`` or ``1.000000-100`` (three-digit exponent)."""
    token = token.strip().replace("d", "e").replace("D", "E")
    if "e" not in token.lower():
        token = _FORTRAN_EXPONENT.sub(r"E\1", token)
    return float(token)


def parse_header(column: str) -> dict[str, Any]:
    """Split one observation header column into its parts.

    Args:
        column: e.g. ``"Total_Tracer_c [M] outlet (200) (9.975E+00 5.0E-01 5.0E-01)"``; an
            optional column number prefix (``"4-"``) is ignored.

    Returns:
        dict: ``variable, unit, point, cell, x, y, z``; for a column that is not a cell
        observation, ``variable`` is the whole column and the rest are None.
    """
    match = _HEADER.match(column.strip())
    if match is None:
        return dict.fromkeys(["unit", "point", "cell", "x", "y", "z"], None) | {
            "variable": column.strip()
        }
    x, y, z = (fortran_float(value) for value in match["coordinates"].split())
    return {
        "variable": match["variable"].strip(),
        "unit": match["unit"].strip() if match["unit"] is not None else None,
        "point": match["point"],
        "cell": int(match["cell"]),
        "x": x,
        "y": y,
        "z": z,
    }


def _read_file(path: Path) -> pd.DataFrame:
    from pydelling.managers.batch import TIME_UNITS

    with path.open() as stream:
        header = next(csv.reader([stream.readline()], skipinitialspace=True))
        rows = [[fortran_float(token) for token in line.split()] for line in stream if line.strip()]
    header = [column.strip() for column in header if column.strip()]
    time = re.fullmatch(r"Time\s*\[(\w+)\]", header[0])
    if time is None or time[1].lower() not in TIME_UNITS:
        raise ValueError(f"{path.name}: first column must be 'Time [<unit>]', not {header[0]!r}")
    data = np.array(rows, dtype=float).reshape(len(rows), -1)
    if data.shape[1] != len(header):
        raise ValueError(f"{path.name}: {data.shape[1]} values per row for {len(header)} columns")
    seconds = data[:, 0] * TIME_UNITS[time[1].lower()]
    frames = []
    for index, column in enumerate(header[1:], start=1):
        parts = parse_header(column)
        frames.append(pd.DataFrame({"time_s": seconds, **parts, "value": data[:, index]}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def read_observation_files(workdir: str | Path) -> pd.DataFrame:
    """Read every PFLOTRAN observation file of a run (all MPI ranks) into one table.

    Args:
        workdir: Folder where PFLOTRAN ran.

    Returns:
        pd.DataFrame: ``time_s, point, cell, x, y, z, variable, unit, value``, one row per
        time, observed cell and variable.

    Raises:
        ValueError: If there is no observation file or one cannot be parsed.
    """
    workdir = Path(workdir)
    files = sorted({path for pattern in OBSERVATION_FILES for path in workdir.glob(pattern)})
    if not files:
        raise ValueError(f"No PFLOTRAN observation files (*-obs-*.pft) in {workdir}")
    frame = pd.concat([_read_file(path) for path in files], ignore_index=True)[COLUMNS]
    frame["cell"] = frame["cell"].astype("Int64")
    return frame.sort_values(["point", "cell", "variable", "time_s"], kind="stable",
                             ignore_index=True)


def _patterns(value: str | Sequence[str] | None) -> list[str] | None:
    if value is None:
        return None
    return [value] if isinstance(value, str) else list(value)


def observation_regions(study: PflotranStudy) -> list[str]:
    """Names of the regions observed by the deck's ``OBSERVATION`` cards, in file order."""
    names = []
    for card in study.deck.find_all("OBSERVATION"):
        for child in card.children:
            if child.key == "REGION" and child.name:
                names.append(child.name)
    return names


class ObservationPoints(PostprocessCallback):
    """Time series at the deck's observation points, read from PFLOTRAN's ``*-obs-*`` files.

    The deck must define ``OBSERVATION`` cards; this is checked before the study runs.

    Args:
        variables: Variable names or globs, with or without unit (``"Total_*"``,
            ``"Liquid Pressure [Pa]"``); None keeps all.
        points: Observation region names or globs; None keeps all.
        name: Output file stem (``processed/<name>.parquet``).

    Example:
        ```python
        study.add_postprocess(ObservationPoints(variables="Total_*"))
        ```
    """

    def __init__(
        self,
        variables: str | Sequence[str] | None = None,
        points: str | Sequence[str] | None = None,
        name: str = "observations",
    ) -> None:
        self.variables = _patterns(variables)
        self.points = _patterns(points)
        self.name = name

    def options(self) -> dict:
        return {"variables": self.variables, "points": self.points, "name": self.name}

    def validate(self, study: PflotranStudy) -> None:
        regions = observation_regions(study)
        if not regions:
            raise ValueError(
                f"{study.input_file_name} has no OBSERVATION cards; observation points are "
                f"required"
            )
        if self.points and not any(glob_match(region, self.points) for region in regions):
            raise ValueError(
                f"no observation point matches {self.points}; the deck observes {regions}"
            )

    def process(self, workdir: Path, study: PflotranStudy) -> pd.DataFrame:
        frame = read_observation_files(workdir)
        if self.points is not None:
            frame = frame[[glob_match(point, self.points) for point in frame.point]]
            if frame.empty:
                raise ValueError(f"No observation matches points {self.points}")
        if self.variables is not None:
            labels = zip(frame.variable, frame.unit, strict=True)
            keep = [
                glob_match(variable, self.variables)
                or glob_match(f"{variable} [{unit}]", self.variables)
                for variable, unit in labels
            ]
            frame = frame[keep]
            if frame.empty:
                raise ValueError(f"No observation matches variables {self.variables}")
        return frame.reset_index(drop=True)
