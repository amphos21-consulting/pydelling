"""Post-processing callbacks: turn a finished study's outputs into a small table.

A callback is attached to a study (``study.add_postprocess(callback)``) and runs where the
study ran, right after the solver, e.g. on the SSH host of a remote campaign. Only its table
(``<workdir>/processed/<name>.parquet``) has to travel back, not the raw solver outputs.

- ``validate(study)`` runs where the studies are prepared, before anything is launched.
- ``process(workdir, study)`` runs in the study's working folder and returns a DataFrame.
- ``spec()`` describes the callback as JSON: it is part of the batch identity and rebuilds
  the callback on any worker (``PostprocessCallback.from_spec``).
"""

from __future__ import annotations

import importlib
import os
import re
import traceback
import uuid
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from pydelling.managers.base_study import BaseStudy

PROCESSED_FOLDER = "processed"
SAFE_NAME = re.compile(r"[A-Za-z0-9_-]+")


def object_path(obj: Any) -> str:
    """Import path of a class or function, ``module:qualname``.

    Args:
        obj: A class or a function defined at module level.

    Returns:
        str: e.g. ``"pydelling.managers.postprocess.hdf5:ExtractHDF5"``.
    """
    return f"{obj.__module__}:{obj.__qualname__}"


def import_object(path: str) -> Any:
    """Import the object named by :func:`object_path`.

    Args:
        path: ``module:qualname``.

    Returns:
        Any: The class or function.

    Raises:
        ValueError: If the path is malformed or names a local object (``<lambda>``, ``<locals>``).
        ImportError: If the module cannot be imported.
    """
    module, _, qualname = path.partition(":")
    if not module or not qualname or "<" in qualname:
        raise ValueError(f"Cannot import {path!r}: use a class or function defined in a module")
    obj: Any = importlib.import_module(module)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


class PostprocessCallback:
    """Base class of post-processing callbacks.

    Subclasses set ``name`` (the output file stem), implement :meth:`process` and
    :meth:`options` (the JSON keyword arguments that rebuild them), and optionally
    :meth:`validate`.

    Example:
        ```python
        class MaxPressure(PostprocessCallback):
            def __init__(self, name: str = "max_pressure") -> None:
                self.name = name

            def options(self) -> dict:
                return {"name": self.name}

            def process(self, workdir: Path, study: BaseStudy) -> pd.DataFrame:
                ...

        study.add_postprocess(MaxPressure())
        ```
    """

    name: str = "postprocess"

    def validate(self, study: BaseStudy) -> None:
        """Check the callback against the study before it runs; raise ``ValueError`` if not.

        Args:
            study: The study the callback is attached to (inputs only, nothing has run).
        """

    def process(self, workdir: Path, study: BaseStudy) -> pd.DataFrame:
        """Read the outputs in ``workdir`` and return the table to keep.

        Args:
            workdir: Folder where the solver ran (the study's inputs and outputs).
            study: The study that ran.

        Returns:
            pd.DataFrame: The data brought back to the host.
        """
        raise NotImplementedError

    def options(self) -> dict:
        """Keyword arguments that rebuild this callback; JSON values only.

        Returns:
            dict: ``type(self)(**options())`` must be equivalent to ``self``.
        """
        return {"name": self.name}

    def spec(self) -> dict:
        """JSON description of the callback (batch identity and remote rebuild).

        Returns:
            dict: ``{"type": "module:Class", "options": {...}}``.
        """
        return {"type": object_path(type(self)), "options": self.options()}

    @staticmethod
    def from_spec(spec: dict) -> PostprocessCallback:
        """Rebuild a callback from :meth:`spec`.

        Args:
            spec: ``{"type": "module:Class", "options": {...}}``.

        Returns:
            PostprocessCallback: A new callback.

        Raises:
            TypeError: If the type is not a ``PostprocessCallback``.
        """
        cls = import_object(spec["type"])
        if not (isinstance(cls, type) and issubclass(cls, PostprocessCallback)):
            raise TypeError(f"{spec['type']} is not a PostprocessCallback")
        return cls(**spec.get("options", {}))

    def __repr__(self) -> str:
        options = ", ".join(f"{k}={v!r}" for k, v in self.options().items())
        return f"{type(self).__name__}({options})"


class FunctionCallback(PostprocessCallback):
    """A plain function used as a callback.

    Args:
        function: ``function(workdir, study) -> DataFrame``, or its ``"module:name"``. Only
            functions defined in a module can be rebuilt from a spec on another worker.
        name: Output file stem.

    Example:
        ```python
        def final_mass(workdir: Path, study: BaseStudy) -> pd.DataFrame: ...

        study.add_postprocess(FunctionCallback(final_mass, name="mass"))
        ```
    """

    def __init__(self, function: Callable[[Path, BaseStudy], pd.DataFrame] | str, name: str) -> None:
        self.function = import_object(function) if isinstance(function, str) else function
        self.name = name

    def options(self) -> dict:
        return {"function": object_path(self.function), "name": self.name}

    def process(self, workdir: Path, study: BaseStudy) -> pd.DataFrame:
        return self.function(workdir, study)


def glob_match(name: str | None, patterns: Sequence[str]) -> bool:
    """Whether ``name`` matches a pattern where only ``*`` and ``?`` are wildcards.

    Brackets are literal, so ``"Liquid Pressure [Pa]"`` matches itself (unlike ``fnmatch``).
    """
    if name is None:
        return False
    for pattern in patterns:
        regex = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
        if re.fullmatch(regex, name):
            return True
    return False


def check_name(name: str) -> str:
    """Return ``name`` if it is a safe file stem, else raise ``ValueError``."""
    if not isinstance(name, str) or not SAFE_NAME.fullmatch(name):
        raise ValueError(f"Postprocess callbacks need a safe name ([A-Za-z0-9_-]+), not {name!r}")
    return name


def write_table(frame: pd.DataFrame, path: str | Path) -> None:
    """Write a table as parquet (no index).

    The file appears atomically, so a reader or a resumed run never sees a partial table.

    Args:
        frame: Table to write.
        path: Destination ``.parquet`` file; missing parent folders are created.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    frame.to_parquet(temp, index=False)
    os.replace(temp, path)


def run_postprocess(study: BaseStudy, workdir: str | Path) -> dict[str, dict]:
    """Run every callback of a study in its working folder.

    Each table is written to ``workdir/processed/<name>.parquet``. A failing callback does
    not stop the others, so every error is reported at once.

    Args:
        study: Study with callbacks (``study.postprocess``).
        workdir: Folder where the solver ran.

    Returns:
        dict: ``{name: {"state": "completed" | "failed", "file", "rows", "sha256", "error"}}``;
        ``file`` is relative to ``workdir``.
    """
    from pydelling.managers.batch import file_hash

    workdir = Path(workdir)
    records = {}
    for callback in getattr(study, "postprocess", []):
        file = f"{PROCESSED_FOLDER}/{callback.name}.parquet"
        record: dict[str, Any] = {"state": "failed", "file": file, "rows": None, "sha256": None}
        try:
            frame = callback.process(workdir, study)
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(
                    f"{type(callback).__name__}.process must return a pandas DataFrame, "
                    f"not {type(frame).__name__}"
                )
            write_table(frame, workdir / file)
            record.update(state="completed", rows=len(frame), sha256=file_hash(workdir / file))
            record["error"] = None
        except Exception as exc:  # noqa: BLE001 -- recorded per callback, reported by the caller
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["traceback"] = traceback.format_exc(limit=5)
        records[callback.name] = record
    return records


def processed_intact(study: BaseStudy, workdir: str | Path, records: dict | None) -> bool:
    """Whether every callback of a study has a completed, unchanged table.

    Args:
        study: Study with callbacks.
        workdir: Folder where the solver ran.
        records: ``status.json["postprocess"]`` of that run, or None.

    Returns:
        bool: True if all tables exist with their recorded hashes (always True without
        callbacks).
    """
    from pydelling.managers.batch import file_hash

    names = [callback.name for callback in getattr(study, "postprocess", [])]
    if not names:
        return True
    if not records or set(records) != set(names):
        return False
    for record in records.values():
        path = Path(workdir) / record["file"]
        if record["state"] != "completed" or not path.is_file():
            return False
        if file_hash(path) != record["sha256"]:
            return False
    return True


def validate_postprocess(studies: Iterable[BaseStudy]) -> None:
    """Validate every callback of every study before anything runs.

    Args:
        studies: Studies with callbacks.

    Raises:
        ValueError: ``"<study>: <callback>: <reason>"`` for the first invalid callback.
    """
    for study in studies:
        for callback in getattr(study, "postprocess", []):
            try:
                callback.validate(study)
                callback.spec()
            except (ValueError, KeyError, TypeError, OSError) as exc:
                raise ValueError(f"{study.name}: {callback.name}: {exc}") from exc
