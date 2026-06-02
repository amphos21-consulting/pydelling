"""
Module documentation.


"""

import numpy as np

from pydelling.readers.iGPReader.geometry import BaseFace


class TriangleFace(BaseFace):
    def __init__(self, nodes, coords):
        """
        __init__ method.
        
        Args:
            nodes (Any): Description.
            coords (Any): Description.
        """
        super().__init__(nodes, coords)
        self.type = "Triangle"

    def compute_centroid(self):
        return np.mean(self.coords, axis=0)
