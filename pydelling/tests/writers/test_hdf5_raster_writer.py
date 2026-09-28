import unittest

from pydelling.interpolation import BaseInterpolator
from pydelling.writers import HDF5RasterWriter
import numpy as np
import h5py
import pytest

class SparseDataInterpolatorCase(unittest.TestCase):
    def test_set_up(self):
        x = np.linspace(0, 1, 100)
        y = np.linspace(0, 1, 100)
        xx, yy = np.meshgrid(x, y)
        z = np.sin(xx ** 2 + yy ** 2)
        raster_writer = HDF5RasterWriter(
            filename='test.h5',
            dataset_name='test',
            x_min=0,
            x_max=1,
            y_min=0,
            y_max=1,
            n_x=100,
            n_y=100,
            data=z,
        )
        raster_writer.run()
        # Open the file
        with h5py.File('test.h5', 'r') as f:
            self.assertIn('test', f.keys())
            data = f['test']['Data']
            self.assertEqual(data.shape, (100, 100, 1))


    def tearDown(self) -> None:
        import os
        os.remove('test.h5')

if __name__ == '__main__':
    unittest.main()


def test_dilatation_is_applied_once_and_centroid_values_keep_their_positions(tmp_path):
    interpolator = BaseInterpolator(
        interpolation_data=np.array(
            [[0.0, 10.0, 1.0], [2.0, 10.0, 2.0], [0.0, 12.0, 3.0], [2.0, 12.0, 4.0]]
        )
    )
    interpolator.create_regular_mesh(n_x=3, n_y=2, dilatation_factor=2.0)
    centroids = np.column_stack(
        [
            interpolator.mesh,
            np.arange(1.0, 7.0),
        ]
    )
    output = tmp_path / "dilatated.h5"

    writer = HDF5RasterWriter(
        filename=output,
        dataset_name="test",
        data=centroids,
        interpolation_info=interpolator.info,
    )
    writer.run()

    with h5py.File(output, "r") as h5_file:
        group = h5_file["test"]
        np.testing.assert_allclose(group.attrs["Discretization"], [2.0, 4.0])
        np.testing.assert_allclose(group.attrs["Origin"], [-1.0, 9.0])
        assert group["Data"].shape == (3, 2, 1)
        np.testing.assert_array_equal(
            group["Data"][:, :, 0],
            [[1.0, 4.0], [2.0, 5.0], [3.0, 6.0]],
        )


def test_direct_grid_metadata_uses_node_spacing_for_rectangular_data(tmp_path):
    output = tmp_path / "rectangular.h5"
    data = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

    writer = HDF5RasterWriter(
        filename=output,
        dataset_name="test",
        data=data,
        n_x=3,
        n_y=2,
        x_min=0.0,
        x_max=2.0,
        y_min=10.0,
        y_max=12.0,
        dilatation_factor=2.0,
    )
    writer.run()

    with h5py.File(output, "r") as h5_file:
        group = h5_file["test"]
        np.testing.assert_allclose(group.attrs["Discretization"], [2.0, 4.0])
        np.testing.assert_allclose(group.attrs["Origin"], [-1.0, 9.0])
        np.testing.assert_array_equal(
            group["Data"][:, :, 0],
            [[1.0, 4.0], [2.0, 5.0], [3.0, 6.0]],
        )


@pytest.mark.parametrize("factor", [0.0, -1.0, np.nan, np.inf])
def test_writer_rejects_invalid_dilatation_factor(tmp_path, factor):
    with pytest.raises(ValueError, match="dilatation_factor"):
        HDF5RasterWriter(
            filename=tmp_path / "invalid.h5",
            dataset_name="test",
            data=np.ones((2, 2)),
            n_x=2,
            n_y=2,
            x_min=0.0,
            x_max=1.0,
            y_min=0.0,
            y_max=1.0,
            dilatation_factor=factor,
        )
