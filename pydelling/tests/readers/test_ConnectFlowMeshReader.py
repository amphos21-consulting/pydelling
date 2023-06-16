import unittest
from pydelling.readers import ConnectFlowMeshReader
from pydelling.utils import test_data_path


class ConnectFlowMeshReaderCase(unittest.TestCase):
    def test_read_data(self):
        connect_flow_reader = ConnectFlowMeshReader(test_data_path() / "connect_flow_reader_data.msh")
        self.assertEqual(connect_flow_reader.n_nodes, 64)
        self.assertEqual(connect_flow_reader.n_elements, 27)

if __name__ == '__main__':
    unittest.main()