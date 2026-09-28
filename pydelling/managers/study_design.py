"""Reproducible, solver-independent parameter designs (no execution side effects)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import qmc


@dataclass(frozen=True)
class SamplingConfig:
    method: str
    n: int | None = None
    seed: int = 0
    options: dict = field(default_factory=dict)


_SAMPLERS: dict[str, Callable] = {}


def register_sampler(name: str, sampler: Callable):
    """Register (n, dimension, seed, **options) -> unit-cube ndarray."""
    if name in _SAMPLERS or name in {"random", "lhs", "sobol", "grid"}:
        raise ValueError(f"Sampler already registered: {name}")
    _SAMPLERS[name] = sampler


class ParameterSpace:
    """Ordered physical marginals; fixed, values, bounds or weighted intervals.

    ``partition: {count: 4, scale: log}`` subdivides bounds. ``scale`` controls
    interpolation *within* intervals independently of partition spacing.
    """

    def __init__(self, parameters: dict):
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
    def _intervals(spec):
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

    def _map(self, spec, u):
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

    def sample(self, config: SamplingConfig) -> pd.DataFrame:
        names = list(self.parameters)
        active = [name for name in names if "fixed" not in self.parameters[name]]
        if config.method == "grid":
            levels = config.options.get("levels", {})
            axes = []
            for name, spec in self.parameters.items():
                values = (
                    [spec["fixed"]] if "fixed" in spec else levels.get(name, spec.get("values"))
                )
                if values is None:
                    raise ValueError(f"Grid requires explicit physical levels for {name}")
                axes.append(values)
            frame = pd.DataFrame(product(*axes), columns=names, dtype=float)
            if config.n is not None and config.n != len(frame):
                raise ValueError(f"Grid has {len(frame)} samples, not {config.n}")
        else:
            n = config.n
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                raise ValueError("Sampling requires an explicit positive integer n")
            d = len(active)
            if config.method == "sobol" and n & (n - 1):
                raise ValueError("Sobol n must be a power of two")
            if config.method not in {"random", "lhs", "sobol"} | _SAMPLERS.keys():
                raise ValueError(f"Unknown sampler: {config.method}")
            if not d:
                points = np.empty((n, 0))
            elif config.method == "random":
                if config.options:
                    raise ValueError("random has no additional options")
                points = np.random.default_rng(config.seed).random((n, d))
            elif config.method == "lhs":
                points = qmc.LatinHypercube(d, seed=config.seed, **config.options).random(n)
            elif config.method == "sobol":
                points = qmc.Sobol(d, seed=config.seed, **config.options).random_base2(
                    n.bit_length() - 1
                )
            else:
                points = np.asarray(_SAMPLERS[config.method](n, d, config.seed, **config.options))
            if (
                points.shape != (n, d)
                or not np.isfinite(points).all()
                or np.any((points < 0) | (points > 1))
            ):
                raise ValueError("Sampler must return a finite (n, dimension) unit-cube array")
            frame = pd.DataFrame(
                {
                    name: self._map(
                        spec, points[:, active.index(name)] if name in active else np.zeros(n)
                    )
                    for name, spec in self.parameters.items()
                }
            )
        return self.validate(frame)

    def validate(self, frame: pd.DataFrame) -> pd.DataFrame:
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
    def export_csv(frame: pd.DataFrame, path: str | Path):
        frame.to_csv(path, index=False, float_format="%.17g")
