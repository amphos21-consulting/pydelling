import unittest

import numpy as np

from pydelling.preprocessing.mesh_preprocessor import generate_structured_mesh


class TestMeshPreprocessor(unittest.TestCase):
    def test_ncells(self):
        test_mesh_preprocessor = generate_structured_mesh([[0, 0, 0], [4, 4, 4]], 4, 4, 4)
        self.assertEqual(test_mesh_preprocessor.n_elements,4*4*4)
        self.assertEqual(test_mesh_preprocessor.n_nodes,5*5*5)
    def test_centroid(self):
        test_mesh_preprocessor = generate_structured_mesh([[0,0,0],[4,4,4]],4,4,4)
        self.assertEqual(test_mesh_preprocessor.elements[58].centroid[0],2.5)
        self.assertEqual(test_mesh_preprocessor.elements[58].centroid[1], 2.5)
        self.assertEqual(test_mesh_preprocessor.elements[58].centroid[2], 3.5)

    def test_nodes(self):
        test_mesh_preprocessor = generate_structured_mesh([[0,0,0],[4,4,4]],4,4,4)
        self.assertEqual(test_mesh_preprocessor.nodes[57][0],3)
        self.assertEqual(test_mesh_preprocessor.nodes[57][1], 1)
        self.assertEqual(test_mesh_preprocessor.nodes[57][2], 2)


if __name__ == '__main__':
    unittest.main()