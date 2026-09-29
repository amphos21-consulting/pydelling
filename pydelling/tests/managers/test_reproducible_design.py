import numpy as np
import pandas as pd
import pytest

from pydelling.managers import LHS, Grid, ParameterSpace, Random, Sampler, Sobol


@pytest.mark.parametrize("method", [Random, LHS, Sobol])
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
    a = method(16, seed=42).sample(space).samples
    pd.testing.assert_frame_equal(a, method(16, seed=42).sample(space).samples)
    assert not a.equals(method(16, seed=43).sample(space).samples)
    space.export_csv(a, tmp_path / "samples.csv")
    pd.testing.assert_frame_equal(a, space.import_csv(tmp_path / "samples.csv"), check_exact=True)


def test_weighted_intervals():
    space = ParameterSpace({"x": {"intervals": [[1, 2], [10, 20]], "weights": [1, 3]}})
    values = LHS(400, seed=1).sample(space).samples.x
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
        Sobol(3)
    result = Grid(levels={"x": [1, 5, 10]}).sample(space).samples
    assert result.x.tolist() == [1, 5, 10] and result.y.tolist() == [3, 3, 3]
    with pytest.raises(ValueError, match="levels"):
        Grid().sample(space)
    with pytest.raises(ValueError):
        space.import_csv(__file__)


@pytest.mark.parametrize("n", [-1, 2.5, True, None])
def test_sample_size_must_be_a_nonnegative_integer(n):
    with pytest.raises(ValueError, match="integer"):
        LHS(n)


def test_zero_samples_give_an_empty_design():
    design = LHS(0).sample({"x": {"bounds": [1, 10]}, "y": {"fixed": 3}})
    assert len(design) == 0 and list(design.samples) == ["x", "y"]


def test_custom_sampler():
    class Midpoints(Sampler):
        def points(self, dimension):
            return np.full((self.n, dimension), 0.5)

    design = Midpoints(2).sample({"x": {"bounds": [1, 100], "scale": "log"}})
    assert np.allclose(design.samples.x, 10) and design.method == "midpoints"
