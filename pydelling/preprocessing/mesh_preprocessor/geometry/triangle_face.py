"""
Module documentation.


"""

import numpy as np

from pydelling.preprocessing.mesh_preprocessor.geometry import BaseFace


class TriangleFace(BaseFace):
    """Triangular mesh face with edge connectivity helpers.

    Category: mesh geometry.
    Tags: triangle, face, edges, centroid, mesh-preprocessor.
    Use when: an MCP agent needs to recognize three-node faces produced by the
        mesh preprocessor and inspect their edge topology.
    """

    def __init__(self, node_ids, node_coords, *args, **kwargs):
        """Create a triangular face from three node ids and coordinates.

        Category: mesh geometry.
        Tags: triangle, face, nodes, coordinates.
        Use when: constructing a mesh-preprocessor face for triangular
            boundaries or element sides.
        Args:
            node_ids: Connectivity ids for the three face nodes.
            node_coords: Coordinate array for the three face vertices.
            *args: Positional arguments forwarded to ``BaseFace``.
            **kwargs: Keyword arguments forwarded to ``BaseFace``.
        Side effects:
            Initializes base face geometry and sets ``type`` to ``"triangle"``.
        """
        super().__init__(node_ids, node_coords, *args, **kwargs)
        self.type = "triangle"

    def compute_centroid(self):
        """Return the arithmetic mean centroid of the triangle vertices.

        Category: mesh geometry.
        Tags: triangle, centroid, coordinates.
        Use when: geometric processing needs a representative point for a
            triangular face.
        Returns:
            np.ndarray: Mean coordinate of the triangle vertices.
        """
        return np.mean(self.coords, axis=0)

    @property
    def edges(self):
        """Return the three directed node-id edges of the triangle.

        Category: mesh geometry.
        Tags: triangle, edges, connectivity.
        Use when: matching, comparing, or exporting triangular face edges.
        Returns:
            list: Three ``[start_node, end_node]`` edge pairs.
        """
        return [
            [self.nodes[0], self.nodes[1]],
            [self.nodes[1], self.nodes[2]],
            [self.nodes[2], self.nodes[0]]
        ]

    @property
    def edge_vectors(self):
        """Return coordinate vectors for each triangle edge.

        Category: mesh geometry.
        Tags: triangle, edges, vectors, coordinates.
        Use when: computing lengths, normals, or geometric checks for a
            triangular face.
        Returns:
            list: Three vectors following the face edge order.
        """
        return [
            self.coords[1] - self.coords[0],
            self.coords[2] - self.coords[1],
            self.coords[0] - self.coords[2]
        ]
