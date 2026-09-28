import numpy as np
import pandas as pd
import pytest

from pydelling.managers import ParameterSpace, SamplingConfig, register_sampler


@pytest.mark.parametrize("method", ["random", "lhs", "sobol"])
def test_seed_and_round_trip(method, tmp_path):
    space = ParameterSpace(
        {
            "K": {
                "bounds": [1e-6, 1e-3],
                "scale": "log",
                "partition": {"count": 3, "scale": "log"},
            },
            "phi": {"bounds": [0.1, 0.5]},
            "fixed": {"fixed": 3},
        }
    )
    a = space.sample(SamplingConfig(method, 16, 42))
    pd.testing.assert_frame_equal(a, space.sample(SamplingConfig(method, 16, 42)))
    assert not a.equals(space.sample(SamplingConfig(method, 16, 43)))
    space.export_csv(a, tmp_path / "samples.csv")
    pd.testing.assert_frame_equal(a, space.import_csv(tmp_path / "samples.csv"), check_exact=True)


def test_weighted_intervals():
    space = ParameterSpace({"x": {"intervals": [[1, 2], [10, 20]], "weights": [1, 3]}})
    values = space.sample(SamplingConfig("lhs", 400, 1)).x
    assert (values < 3).sum() == 100
    assert not ((values > 2) & (values < 10)).any()


@pytest.mark.parametrize(
    "spec",
    [
        {"bounds": [0, 1], "scale": "log"},
        {"bounds": [1, 0]},
        {"intervals": [[1, 4], [2, 5]]},
        {"intervals": [[1, 2]], "weights": [0]},
        {"fixed": float("nan")},
        {"values": []},
        {"bounds": [1, 2], "fixed": 2},
    ],
)
def test_invalid_space(spec):
    with pytest.raises(ValueError):
        ParameterSpace({"x": spec})


def test_sobol_and_grid_sizes():
    space = ParameterSpace({"x": {"bounds": [1, 10]}, "y": {"fixed": 3}})
    with pytest.raises(ValueError, match="power of two"):
        space.sample(SamplingConfig("sobol", 3))
    result = space.sample(SamplingConfig("grid", options={"levels": {"x": [1, 5, 10]}}))
    assert result.x.tolist() == [1, 5, 10]
    with pytest.raises(ValueError):
        space.sample(SamplingConfig("grid", 4, options={"levels": {"x": [1, 5, 10]}}))
    with pytest.raises(ValueError):
        space.import_csv(__file__)


def test_custom_sampler():
    register_sampler("test-midpoints", lambda n, d, seed: np.full((n, d), 0.5))
    result = ParameterSpace({"x": {"bounds": [1, 100], "scale": "log"}}).sample(
        SamplingConfig("test-midpoints", 2)
    )
    assert np.allclose(result.x, 10)
