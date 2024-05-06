import unittest
import numpy as np
from pathlib import Path
from pydelling.readers.FeflowReader import FeflowReader
from pydelling.utils import test_data_path


class FeflowReaderCase(unittest.TestCase):

    def test_feflowreader(self):
        """ Test class method read_field_dat. """
        path = Path(__file__).parent.parent / "test_data/concentration_5nodes.dat"
        reader = FeflowReader()
        data = reader.read_field_dat(path)
        concentration_reader = data["Concentration"]
        concentration_real = np.array([1.646512375E-08,
                                       1.461990002E-08,
                                       1.324807445E-08,
                                       1.356132066E-08,
                                       1.375429918E-08])

        self.assertTrue(np.allclose(concentration_reader, concentration_real, rtol=1e-05, atol=1e-08))

    def test_compute_diff_2fields(self):
        """ Test class method compute_diff_2fields."""
        path = Path(__file__).parent.parent / "test_data/concentration_5nodes.dat"
        reader = FeflowReader()
        field1 = reader.read_field_dat(path)
        field2 = reader.read_field_dat(path)
        diff_field = reader.compute_diff_2fields(field1, field2, "Concentration")
        # self.assert_allclose(diff_field["Concentration"], 0, atol=1e-07)
        self.assertTrue(
            np.allclose(diff_field["Diff"], np.zeros(len(diff_field["Diff"])),
                        rtol=1e-05,
                        atol=1e-08)
        )

    def test_set_head_bc(self):
        """ Test method set_head_bc """
        reader = FeflowReader()
        z_coord = np.array([0., -100., -1000.])  # water depth
        sea_rise = 1  # sea level rise in meters
        head_new = np.array([1.025, 3.525, 26.025])
        head_comp = reader.set_head_bc(sea_rise, z_coord)
        self.assertTrue(
            np.allclose(head_new, head_comp,
                        rtol=1e-05,
                        atol=1e-08))


if __name__ == '__main__':
    unittest.main()