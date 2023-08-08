import unittest
from pydelling.readers import ConnectFlowMeshReader
from pydelling.utils import test_data_path


class TestConnectFlowMeshReader(unittest.TestCase):
    def test_read_data(self):
        pass
        path = test_data_path() / 'test_file.msh'
        # self.assertEqual(4, len(Pf))




if __name__ == '__main__':
    unittest.main()