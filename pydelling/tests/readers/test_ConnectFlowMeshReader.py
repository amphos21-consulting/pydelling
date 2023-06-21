import unittest
from pydelling.readers import ConnectFlowMeshReader
from pydelling.utils import test_data_path


class ConnectFlowMeshReaderCase(unittest.TestCase):
    def setUp(self) -> None:
        self.connect_flow_reader = ConnectFlowMeshReader(test_data_path() / "connect_flow_reader_data.msh")

    def test_read_data(self):
        self.assertEqual(self.connect_flow_reader.n_nodes, 64)
        self.assertEqual(self.connect_flow_reader.n_elements, 27)

    def test_connectivities(self):
        pass

if __name__ == '__main__':
    unittest.main()