import unittest

from pydelling.writers import HDF5RasterWriter
import numpy as np
import h5py

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

