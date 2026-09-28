import unittest
from pydelling.interpolation import BaseInterpolator
from pydelling.readers import iGPReader, CentroidReader
from pydelling.utils import test_data_path
import numpy
import pytest
import h5py


class BaseInterpolatorCase(unittest.TestCase):
    def setUp(self) -> None:
        self.mesh_data = iGPReader(test_data_path() / "test_implicit_to_explicit.gid", project_name="test").get_mesh()
        self.interpolation_data = CentroidReader(test_data_path() / "centroid_reader_data.csv", separator=",", header=True).get_data()
        self.base_interpolator = BaseInterpolator(mesh_data=self.mesh_data, interpolation_data=self.interpolation_data)

    def test_set_up(self):
        numpy.testing.assert_array_equal(self.base_interpolator.mesh, self.mesh_data)
        numpy.testing.assert_array_equal(self.base_interpolator.data, self.interpolation_data)

    def test_interpolation(self):
        interpolated_data = self.base_interpolator.run()
        numpy.testing.assert_array_equal(interpolated_data, self.mesh_data[:, 0])


def test_create_regular_mesh_dilatates_domain_about_its_center():
    data = numpy.array([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 10.0],
        [0.0, 4.0, 4.0],
        [10.0, 4.0, 14.0],
    ])
    interpolator = BaseInterpolator(interpolation_data=data)

    interpolator.create_regular_mesh(n_x=6, n_y=3, dilatation_factor=1.5)

    x = numpy.unique(interpolator.mesh[:, 0])
    y = numpy.unique(interpolator.mesh[:, 1])
    numpy.testing.assert_allclose(x, [-2.5, 0.5, 3.5, 6.5, 9.5, 12.5])
    numpy.testing.assert_allclose(y, [-1.0, 2.0, 5.0])
    assert interpolator.info["interpolation"]["d_x"] == pytest.approx(3.0)
    assert interpolator.info["interpolation"]["d_y"] == pytest.approx(3.0)


@pytest.mark.parametrize(
    ("n_x", "n_y", "dilatation_factor"),
    [
        (1, 3, 1.0),
        (3, 1, 1.0),
        (3, 3, 0.0),
        (3, 3, -1.0),
        (3, 3, numpy.inf),
    ],
)
def test_create_regular_mesh_rejects_invalid_grid_parameters(
    n_x, n_y, dilatation_factor
):
    interpolator = BaseInterpolator(
        interpolation_data=numpy.array([[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]])
    )

    with pytest.raises(ValueError):
        interpolator.create_regular_mesh(
            n_x=n_x,
            n_y=n_y,
            dilatation_factor=dilatation_factor,
        )


def test_add_mesh_appends_coordinates_and_keeps_ids_flat():
    interpolator = BaseInterpolator()

    interpolator.add_mesh(
        numpy.array([[0.0, 1.0, 2.0, 10], [3.0, 4.0, 5.0, 11]])
    )
    interpolator.add_mesh(numpy.array([[6.0, 7.0, 8.0, 12]]))

    numpy.testing.assert_array_equal(
        interpolator.mesh,
        [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0], [6.0, 7.0, 8.0]],
    )
    numpy.testing.assert_array_equal(interpolator.id_data, [10, 11, 12])


def test_add_mesh_honors_non_default_id_column():
    interpolator = BaseInterpolator()

    interpolator.add_mesh(numpy.array([[10, 1.0, 2.0, 3.0]]), id_index=0)

    numpy.testing.assert_array_equal(interpolator.mesh, [[1.0, 2.0, 3.0]])
    numpy.testing.assert_array_equal(interpolator.id_data, [10])


def test_input_changes_invalidate_previous_interpolation_results():
    interpolator = BaseInterpolator(
        interpolation_data=numpy.array([[0.0, 0.0, 1.0], [1.0, 1.0, 2.0]]),
        mesh_data=numpy.array([[0.25, 0.25], [0.75, 0.75]]),
    )
    interpolator.run()
    assert interpolator.is_run

    interpolator.add_data(numpy.array([[2.0, 2.0, 3.0]]))

    assert not interpolator.is_run
    assert interpolator.interpolated_data.size == 0


def test_wipe_data_resets_mesh_metadata_and_state():
    interpolator = BaseInterpolator(
        interpolation_data=numpy.array(
            [[0.0, 0.0, 1.0], [1.0, 0.0, 2.0], [0.0, 1.0, 3.0], [1.0, 1.0, 4.0]]
        )
    )
    interpolator.create_regular_mesh(2, 2)
    interpolator.run()

    interpolator.wipe_data()

    assert interpolator.data.size == 0
    assert interpolator.mesh.size == 0
    assert interpolator.interpolated_data.size == 0
    assert not interpolator.is_run
    assert not interpolator.has_regular_mesh
    assert interpolator.info == {"interpolation": {}}


def test_dump_to_hdf5_replaces_an_existing_dataset(tmp_path):
    output = tmp_path / "interpolation.h5"
    interpolator = BaseInterpolator()

    interpolator.dump_to_hdf5(output, "values", data=numpy.array([1.0, 2.0]))
    interpolator.dump_to_hdf5(var_name="values", data=numpy.array([3.0, 4.0]))

    with h5py.File(output, "r") as h5_file:
        numpy.testing.assert_array_equal(h5_file["values"][:], [3.0, 4.0])


if __name__ == '__main__':
    unittest.main()
