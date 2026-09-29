"""Reproducible parameter samplings, independent of any solver.

Three pieces, each with one job:

- :class:`ParameterSpace` says which parameters exist and their allowed ranges.
- A sampler (:class:`LHS`, :class:`Sobol`, :class:`Random`, :class:`Grid`, :class:`Table`
  or your own :class:`Sampler` subclass) says how samples are drawn.
- :class:`Design` is the result: a named, validated table of samples.

Most code never handles a design: ``manager.add_studies(sampler, space, template)`` draws
the samples and adds one study per sample.

Example:
    ```python
    space = ParameterSpace({"K": {"bounds": [1e-6, 1e-3], "scale": "log"}})
    manager.add_studies(LHS(n=16, seed=42), space, template)   # swap LHS for Sobol, ...
    LHS(n=16, seed=42).sample(space)                            # just the samples
    ```
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import qmc


class ParameterSpace:
    """Uncertain parameters in physical units, each defined by one of its options.

    Every value this space produces or imports is checked against these definitions, so
    code using the samples does not need to re-validate ranges.

    Args:
        parameters: Mapping of parameter name to a definition with exactly one of

            - ``fixed``: a constant, e.g. ``{"fixed": 1.0}``;
            - ``values``: equiprobable discrete values, e.g. ``{"values": [0.1, 0.3]}``;
            - ``bounds``: a continuous range, e.g. ``{"bounds": [1e-6, 1e-3], "scale": "log"}``;
            - ``intervals``: disjoint ranges with relative ``weights``.

            ``scale`` (``linear``/``log``) sets the distribution within ranges;
            ``partition: {count: 3, scale: log}`` splits ``bounds`` into weighted intervals;
            ``units`` is documentation only.

    Raises:
        ValueError: If a definition is empty, ambiguous or inconsistent.

    Example:
        ```python
        space = ParameterSpace({
            "K": {"bounds": [1e-6, 1e-3], "scale": "log", "units": "m/s"},
            "porosity": {"bounds": [0.1, 0.5]},
        })
        ```
    """

    def __init__(self, parameters: dict) -> None:
        if not parameters:
            raise ValueError("At least one parameter is required")
        self.parameters = parameters
        for name, spec in parameters.items():
            if not isinstance(spec, dict):
                raise TypeError(f"{name}: expected a parameter mapping")
            allowed = {
                "fixed",
                "values",
                "bounds",
                "intervals",
                "partition",
                "scale",
                "weights",
                "units",
            }
            unknown = set(spec) - allowed
            if unknown:
                raise ValueError(f"{name}: unknown parameter options {sorted(unknown)}")
            choices = sum(k in spec for k in ("fixed", "values", "bounds", "intervals"))
            if choices != 1:
                raise ValueError(f"{name}: choose fixed, values, bounds or intervals")
            if "fixed" in spec:
                if not np.isfinite(float(spec["fixed"])):
                    raise ValueError(f"{name}: fixed value must be finite")
            elif "values" in spec:
                values = np.asarray(spec["values"], dtype=float)
                if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
                    raise ValueError(f"{name}: values must be a finite nonempty list")
            else:
                self._intervals(spec)

    @staticmethod
    def _intervals(spec: dict) -> tuple[np.ndarray, np.ndarray, str]:
        scale = spec.get("scale", "linear")
        if scale not in ("linear", "log"):
            raise ValueError("Scale must be linear or log")
        if "intervals" in spec:
            intervals = np.asarray(spec["intervals"], dtype=float)
        else:
            low, high = map(float, spec["bounds"])
            partition = spec.get("partition", {})
            count = partition.get("count", 1)
            if not isinstance(count, int) or count < 1:
                raise ValueError("Partition count must be a positive integer")
            spacing = partition.get("scale", "linear")
            if spacing not in ("linear", "log") or (spacing == "log" and low <= 0):
                raise ValueError("Invalid partition scale/bounds")
            edges = (np.geomspace if spacing == "log" else np.linspace)(low, high, count + 1)
            intervals = np.column_stack((edges[:-1], edges[1:]))
        if intervals.ndim != 2 or intervals.shape[1] != 2 or not len(intervals):
            raise ValueError("Intervals must be a nonempty list of [low, high]")
        if not np.isfinite(intervals).all() or np.any(intervals[:, 0] >= intervals[:, 1]):
            raise ValueError("Intervals must be finite and strictly increasing")
        if np.any(intervals[1:, 0] < intervals[:-1, 1]):
            raise ValueError("Intervals must be sorted and non-overlapping")
        if scale == "log" and np.any(intervals <= 0):
            raise ValueError("Logarithmic bounds must be positive")
        weights = np.asarray(spec.get("weights", np.ones(len(intervals))), dtype=float)
        if (
            weights.shape != (len(intervals),)
            or not np.isfinite(weights).all()
            or np.any(weights <= 0)
        ):
            raise ValueError("One finite positive weight is required per interval")
        return intervals, weights / weights.sum(), scale

    def _map(self, spec: dict, u: np.ndarray) -> np.ndarray:
        if "fixed" in spec:
            return np.full(len(u), float(spec["fixed"]))
        if "values" in spec:
            values = np.asarray(spec["values"], dtype=float)
            return values[np.minimum((u * len(values)).astype(int), len(values) - 1)]
        intervals, weights, scale = self._intervals(spec)
        cumulative = np.r_[0.0, np.cumsum(weights)]
        indices = np.minimum(np.searchsorted(cumulative[1:], u, side="right"), len(weights) - 1)
        position = (u - cumulative[indices]) / weights[indices]
        low, high = intervals[indices].T
        if scale == "log":
            return np.exp(np.log(low) + position * (np.log(high) - np.log(low)))
        return low + position * (high - low)

    @property
    def active(self) -> list:
        """Names of the parameters that vary (all but ``fixed`` ones), in order."""
        return [name for name, spec in self.parameters.items() if "fixed" not in spec]

    def from_unit_cube(self, points: np.ndarray) -> pd.DataFrame:
        """Map unit-cube points to physical values.

        Args:
            points: ``(n, len(active))`` array in ``[0, 1]``, one column per varying
                parameter. Each column goes through that parameter's range, scale and
                interval weights; fixed parameters are added as constant columns.

        Returns:
            pandas.DataFrame: One row per point, one column per parameter, validated.
        """
        points = np.asarray(points, dtype=float)
        active = self.active
        return self.validate(
            pd.DataFrame(
                {
                    name: self._map(
                        spec,
                        points[:, active.index(name)] if name in active else np.zeros(len(points)),
                    )
                    for name, spec in self.parameters.items()
                }
            )
        )

    def validate(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Check a table of samples against the parameter definitions.

        Args:
            frame: One column per parameter, in physical units.

        Returns:
            pandas.DataFrame: The table as floats, columns in parameter order.

        Raises:
            ValueError: If columns differ from the parameters, the table is empty, or a
                value is nonfinite or outside its parameter's range.
        """
        if set(frame.columns) != set(self.parameters) or not len(frame):
            raise ValueError("Sample columns must exactly match parameters; table cannot be empty")
        frame = frame[list(self.parameters)].astype(float)
        if not np.isfinite(frame.to_numpy()).all():
            raise ValueError("Samples contain nonfinite values")
        for name, spec in self.parameters.items():
            values = frame[name].to_numpy()
            if "fixed" in spec or "values" in spec:
                valid = np.isin(values, [spec["fixed"]] if "fixed" in spec else spec["values"])
            else:
                intervals, _, _ = self._intervals(spec)
                valid = np.any(
                    [
                        (values >= low * (1 - 1e-14) - 1e-30)
                        & (values <= high * (1 + 1e-14) + 1e-30)
                        for low, high in intervals
                    ],
                    axis=0,
                )
            if not valid.all():
                raise ValueError(f"Samples outside allowed values for {name}")
        return frame

    def import_csv(self, path: str | Path) -> pd.DataFrame:
        return self.validate(pd.read_csv(path, float_precision="round_trip"))

    @staticmethod
    def export_csv(frame: pd.DataFrame, path: str | Path) -> None:
        frame.to_csv(path, index=False, float_format="%.17g")


SAFE_NAME = re.compile(r"[A-Za-z0-9_-]+")


def _space(space: ParameterSpace | dict) -> ParameterSpace:
    return space if isinstance(space, ParameterSpace) else ParameterSpace(space)


@dataclass(frozen=True, eq=False)
class Design:
    """A named, validated table of samples: the result of ``sampler.sample(space)``.

    Iterating yields one ``{parameter: value}`` dict per sample. ``manager.add_studies``
    keeps the design it draws in ``manager.designs`` (e.g. to write it with :meth:`to_csv`).

    Attributes:
        name: Identifier used in study names (``<name>-000000``); ``[A-Za-z0-9_-]+``.
        samples: One row per sample, one column per parameter, in physical units.
        method: Sampler that produced it (``"lhs"``, ``"grid"``, ``"table"``, ...).
        seed: Random seed, or None when the sampler has none.
    """

    name: str
    samples: pd.DataFrame
    method: str = "table"
    seed: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not SAFE_NAME.fullmatch(self.name):
            raise ValueError(f"Design name must match [A-Za-z0-9_-]+, not {self.name!r}")

    def to_csv(self, path: str | Path) -> None:
        """Write the samples with round-trip precision; replay them with :class:`Table`.

        Args:
            path: Destination CSV file.
        """
        ParameterSpace.export_csv(self.samples, path)

    def __len__(self) -> int:
        return len(self.samples)

    def __iter__(self) -> Iterator[dict]:
        return iter(self.samples.to_dict("records"))

    def __repr__(self) -> str:
        seed = "" if self.seed is None else f", seed={self.seed}"
        return f"Design({self.name!r}, {len(self)} samples, method={self.method!r}{seed})"


class Sampler:
    """A sampling method. Use a built-in one or subclass this to write your own.

    A subclass only implements :meth:`points`: ``n`` points in the unit cube, one column
    per varying parameter. :meth:`sample` maps them through each parameter's range, scale
    and weights, validates them and returns a :class:`Design`.

    Args:
        n: Number of samples; 0 gives no samples (e.g. to run only benchmarks).
        seed: Random seed; the same seed gives the same samples.
        name: Design name; defaults to the method (``"lhs"``, ``"halton"``, ...).

    Raises:
        ValueError: If ``n`` is not an integer >= 0.

    Example:
        ```python
        class Halton(Sampler):
            def points(self, dimension: int) -> np.ndarray:
                return scipy.stats.qmc.Halton(dimension, seed=self.seed).random(self.n)

        design = Halton(n=16, seed=1).sample(space)
        ```
    """

    def __init__(self, n: int, seed: int = 0, name: str | None = None) -> None:
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise ValueError(f"{type(self).__name__} needs an integer n >= 0, not {n!r}")
        self.n = n
        self.seed = seed
        self.name = name or self.method

    @property
    def method(self) -> str:
        """Method name recorded with the samples: the class name in lower case."""
        return type(self).__name__.lower()

    def points(self, dimension: int) -> np.ndarray:
        """Draw the samples in the unit cube; override this in a new sampler.

        Args:
            dimension: Number of varying parameters (columns).

        Returns:
            numpy.ndarray: ``(self.n, dimension)`` array with values in ``[0, 1]``.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement points()")

    def table(self, space: ParameterSpace) -> pd.DataFrame:
        """Samples in physical units, validated against ``space``."""
        if self.n == 0:
            return pd.DataFrame(columns=list(space.parameters), dtype=float)
        dimension = len(space.active)
        points = np.asarray(self.points(dimension)) if dimension else np.empty((self.n, 0))
        if (
            points.shape != (self.n, dimension)
            or not np.isfinite(points).all()
            or np.any((points < 0) | (points > 1))
        ):
            raise ValueError(
                f"{type(self).__name__}.points must return a finite ({self.n}, {dimension}) "
                f"array in the unit cube"
            )
        return space.from_unit_cube(points)

    def sample(self, space: ParameterSpace | dict) -> Design:
        """Draw the samples.

        Args:
            space: :class:`ParameterSpace`, or the mapping that defines one.

        Returns:
            Design: The validated samples, named ``self.name``.
        """
        return Design(self.name, self.table(_space(space)), self.method, self.seed)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(n={self.n}, seed={self.seed})"


class Random(Sampler):
    """Independent uniform samples (Monte Carlo)."""

    def points(self, dimension: int) -> np.ndarray:
        return np.random.default_rng(self.seed).random((self.n, dimension))


class LHS(Sampler):
    """Latin hypercube: each parameter's range is split into ``n`` strata, one sample each.

    Args:
        n: Number of samples.
        seed: Random seed.
        name: Design name; defaults to ``"lhs"``.
        **options: Options of ``scipy.stats.qmc.LatinHypercube``, e.g. ``scramble=False``
            or ``optimization="random-cd"``.
    """

    def __init__(self, n: int, seed: int = 0, name: str | None = None, **options) -> None:
        super().__init__(n, seed, name)
        self.options = options

    def points(self, dimension: int) -> np.ndarray:
        return qmc.LatinHypercube(dimension, seed=self.seed, **self.options).random(self.n)


class Sobol(Sampler):
    """Sobol low-discrepancy sequence; ``n`` must be a power of two.

    Args:
        n: Number of samples, a power of two.
        seed: Random seed (for scrambling).
        name: Design name; defaults to ``"sobol"``.
        **options: Options of ``scipy.stats.qmc.Sobol``, e.g. ``scramble=False``.

    Raises:
        ValueError: If ``n`` is not a power of two.
    """

    def __init__(self, n: int, seed: int = 0, name: str | None = None, **options) -> None:
        super().__init__(n, seed, name)
        if n & (n - 1):
            raise ValueError(f"Sobol n must be a power of two, not {n}")
        self.options = options

    def points(self, dimension: int) -> np.ndarray:
        return qmc.Sobol(dimension, seed=self.seed, **self.options).random_base2(
            self.n.bit_length() - 1
        )


class Grid(Sampler):
    """Every combination of the given physical levels (full factorial).

    Args:
        levels: Physical values per varying parameter, e.g. ``{"K": [1e-5, 1e-4]}``.
            Parameters defined by ``values`` use them when not listed; fixed ones are
            constant.
        name: Design name; defaults to ``"grid"``.

    Raises:
        ValueError: When sampling, if a varying parameter has no levels.
    """

    def __init__(self, levels: dict | None = None, name: str | None = None) -> None:
        self.levels = dict(levels or {})
        self.n = None
        self.seed = None
        self.name = name or self.method

    def table(self, space: ParameterSpace) -> pd.DataFrame:
        axes = []
        for name, spec in space.parameters.items():
            values = (
                [spec["fixed"]] if "fixed" in spec else self.levels.get(name, spec.get("values"))
            )
            if values is None:
                raise ValueError(f"Grid requires explicit physical levels for {name}")
            axes.append(values)
        return space.validate(pd.DataFrame(product(*axes), columns=list(space.parameters)))

    def __repr__(self) -> str:
        return f"Grid(levels={self.levels})"


class Table(Sampler):
    """Samples you already have, e.g. a CSV written by :meth:`Design.to_csv`.

    Args:
        samples: A CSV path, a DataFrame or a list of ``{parameter: value}`` dicts, in
            physical units.
        name: Design name; defaults to ``"table"``.

    Raises:
        ValueError: When sampling, if the columns differ from the parameters or a value is
            outside its range.
    """

    def __init__(
        self, samples: str | Path | pd.DataFrame | list[dict], name: str | None = None
    ) -> None:
        self.samples = samples
        self.n = None
        self.seed = None
        self.name = name or self.method

    def table(self, space: ParameterSpace) -> pd.DataFrame:
        if isinstance(self.samples, (str, Path)):
            return space.import_csv(self.samples)
        return space.validate(pd.DataFrame(self.samples))

    def __repr__(self) -> str:
        source = self.samples if isinstance(self.samples, (str, Path)) else "..."
        return f"Table({source!r})"
