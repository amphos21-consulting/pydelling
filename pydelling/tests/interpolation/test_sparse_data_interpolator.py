import unittest
from pydelling.interpolation import SparseDataInterpolator
from pydelling.readers import iGPReader, CentroidReader
from pydelling.utils import test_data_path
import numpy
import pytest


class SparseDataInterpolatorCase(unittest.TestCase):
    def setUp(self) -> None:
        self.mesh_data = iGPReader(test_data_path() / "test_implicit_to_explicit.gid", project_name="test").get_mesh()
        self.interpolation_data = CentroidReader(test_data_path() / "centroid_reader_data.csv", separator=",", header=True).get_data()
        self.base_interpolator = SparseDataInterpolator(mesh_data=self.mesh_data, interpolation_data=self.interpolation_data)

    def test_set_up(self):
        numpy.testing.assert_array_equal(self.base_interpolator.mesh, self.mesh_data)
        numpy.testing.assert_array_equal(self.base_interpolator.data, self.interpolation_data)

    def test_interpolation(self):
        self.base_interpolator.run()


def test_divided_interpolation_preserves_original_mesh_order():
    interpolator = SparseDataInterpolator(
        interpolation_data=numpy.array(
            [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]
        ),
        mesh_data=numpy.array([[3.0], [0.0], [2.0], [1.0]]),
    )

    result = interpolator.run(divide_over_direction=True)

    numpy.testing.assert_array_equal(result[:, 0], [3.0, 0.0, 2.0, 1.0])
    numpy.testing.assert_array_equal(result[:, 1], [3.0, 0.0, 2.0, 1.0])


def test_interpolation_rejects_coordinate_dimension_mismatch():
    interpolator = SparseDataInterpolator(
        interpolation_data=numpy.array([[0.0, 0.0], [1.0, 1.0]]),
        mesh_data=numpy.array([[0.0, 0.0], [1.0, 1.0]]),
    )

    with pytest.raises(ValueError, match="coordinate dimensions"):
        interpolator.run()


def test_change_min_value_requires_results_and_a_finite_threshold():
    interpolator = SparseDataInterpolator(
        interpolation_data=numpy.array([[0.0, -2.0], [1.0, 2.0]]),
        mesh_data=numpy.array([[0.0], [1.0]]),
    )

    with pytest.raises(RuntimeError, match="not been run"):
        interpolator.change_min_value(0.0)

    interpolator.run()
    with pytest.raises(ValueError, match="min_value"):
        interpolator.change_min_value(None)

    numpy.testing.assert_array_equal(interpolator.change_min_value(0.0), [0.0, 2.0])


def test_get_data_requires_current_interpolation_results():
    interpolator = SparseDataInterpolator(
        interpolation_data=numpy.array([[0.0, 1.0], [1.0, 2.0]]),
        mesh_data=numpy.array([[0.5]]),
    )

    with pytest.raises(RuntimeError, match="not been run"):
        interpolator.get_data()


def test_plot_regular_mesh_returns_populated_axes():
    interpolator = SparseDataInterpolator(
        interpolation_data=numpy.array(
            [[0.0, 0.0, 1.0], [1.0, 0.0, 2.0], [0.0, 1.0, 3.0], [1.0, 1.0, 4.0]]
        )
    )
    interpolator.create_regular_mesh(2, 2)
    interpolator.run()

    axes = interpolator.plot_regular_mesh()

    assert axes.collections


def test_failed_rerun_invalidates_previous_values():
    interpolator = SparseDataInterpolator(
        interpolation_data=numpy.array([[0.0, 1.0], [1.0, 2.0]]),
        mesh_data=numpy.array([[0.5]]),
    )
    interpolator.run()

    with pytest.raises(ValueError):
        interpolator.run(method="unsupported")

    assert not interpolator.is_run
    with pytest.raises(RuntimeError, match="not been run"):
        interpolator.get_data()


@pytest.mark.parametrize(
    "interpolation_data",
    [
        numpy.array([[numpy.nan, 1.0], [1.0, 2.0]]),
        numpy.array([[0.0, numpy.nan], [1.0, 2.0]]),
    ],
)
def test_interpolation_rejects_non_finite_source_data(interpolation_data):
    interpolator = SparseDataInterpolator(
        interpolation_data=interpolation_data,
        mesh_data=numpy.array([[0.5]]),
    )

    with pytest.raises(ValueError, match="finite"):
        interpolator.run()


if __name__ == '__main__':
    unittest.main()
