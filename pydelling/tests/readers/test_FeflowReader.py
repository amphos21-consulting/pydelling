import unittest
import numpy as np
from pydelling.readers.FeflowReader import FeflowReader
from pydelling.utils import test_data_path


class FeflowReadertCase(unittest.TestCase):

    def test_feflowreader(self):
        """ Test class method read_field_dat. """
        path = "../test_data/concentration_5nodes.dat"
        reader = FeflowReader()
        data = reader.read_field_dat(path)
        concentration_reader = data["Concentration"]
        concentration_real = np.array([1.646512375E-08,
                                       1.461990002E-08,
                                       1.324807445E-08,
                                       1.356132066E-08,
                                       1.375429918E-08])

        self.assertTrue(np.allclose(concentration_reader, concentration_real, rtol=1e-05, atol=1e-08))


if __name__ == '__main__':
    unittest.main()