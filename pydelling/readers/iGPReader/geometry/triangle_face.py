"""
Module documentation.


"""

import numpy as np

from pydelling.readers.iGPReader.geometry import BaseFace


class TriangleFace(BaseFace):
    """Triangular iGP face storing node ids and coordinates.

    Category: iGP geometry.
    Tags: triangle, face, centroid.
    Use when: to identify triangular boundary faces in iGP
        mesh geometry.
    """

    def __init__(self, nodes, coords):
        """Create a triangular face from connectivity and coordinates.

        Category: iGP geometry.
        Tags: triangle, face, nodes, coordinates.
        Use when: constructing triangular faces for element topology or region
            operations.
        Args:
            nodes: Node ids defining the face.
            coords: Coordinate array for the face vertices.
        Side effects:
            Initializes base face geometry and sets ``type`` to ``"Triangle"``.
        """
        super().__init__(nodes, coords)
        self.type = "Triangle"

    def compute_centroid(self):
        """Return the arithmetic mean centroid of the face vertices.

        Category: iGP geometry.
        Tags: triangle, centroid, coordinates.
        Use when: region and export operations need a representative face point.
        Returns:
            np.ndarray: Mean coordinate of the face vertices.
        """
        return np.mean(self.coords, axis=0)
