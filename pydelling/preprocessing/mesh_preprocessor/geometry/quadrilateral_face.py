"""
Module documentation.


"""

import numpy as np

from pydelling.preprocessing.mesh_preprocessor.geometry import BaseFace


class QuadrilateralFace(BaseFace):
    """Quadrilateral mesh face with edge connectivity helpers.

    Category: mesh geometry.
    Tags: quadrilateral, face, edges, centroid, mesh-preprocessor.
    Use when: an MCP agent needs to recognize four-node faces produced by the
        mesh preprocessor and inspect their edge topology.
    """

    def __init__(self, node_ids, node_coords, *args, **kwargs):
        """Create a quadrilateral face from four node ids and coordinates.

        Category: mesh geometry.
        Tags: quadrilateral, face, nodes, coordinates.
        Use when: constructing a mesh-preprocessor face for quadrilateral
            boundaries or element sides.
        Args:
            node_ids: Connectivity ids for the four face nodes.
            node_coords: Coordinate array for the four face vertices.
            *args: Positional arguments forwarded to ``BaseFace``.
            **kwargs: Keyword arguments forwarded to ``BaseFace``.
        Side effects:
            Initializes base face geometry and sets ``type`` to
            ``"quadrilateral"``.
        """
        super().__init__(node_ids, node_coords, *args, **kwargs)
        self.type = "quadrilateral"

    def compute_centroid(self):
        """Return the arithmetic mean centroid of the quadrilateral vertices.

        Category: mesh geometry.
        Tags: quadrilateral, centroid, coordinates.
        Use when: geometric processing needs a representative point for a
            quadrilateral face.
        Returns:
            np.ndarray: Mean coordinate of the quadrilateral vertices.
        """
        return np.mean(self.coords, axis=0)
        # t1 = [0, 1, 3]
        # t2 = [1, 2, 3]
        # triangles = [t1, t2]
        # poly_centroid = np.zeros(shape=3)
        # for triangle_nodes in triangles:
        #     # Set-up variables
        #     q1 = self.node_coords[triangle_nodes[0]]  # Point1 of small triangle
        #     q2 = self.node_coords[triangle_nodes[1]]  # Point2 of small triangle
        #     q3 = self.node_coords[triangle_nodes[2]]  # Point3 of small triangle
        #     q_v = np.array([q1, q2, q3])
        #     v1 = q2 - q1
        #     v2 = q3 - q1
        #     v_cross = np.cross(v1, v2)
        #     area_triangle = np.linalg.norm(v_cross) / 2.0
        #     # print(f"area triangle:{area_triangle}")
        #     # print(f"Total area:{self.area}")
        #     # Compute centroid
        #     mean_centroid = np.mean(q_v, axis=0)  # Centroid of small triangle
        #     poly_centroid += area_triangle * mean_centroid
        #     # print(f"q1: {q1}, q2: {q2}, q3:{q3}, mean_centroid:{mean_centroid}")
        # return poly_centroid / self.area

    @property
    def edges(self):
        """Return the four directed node-id edges of the quadrilateral.

        Category: mesh geometry.
        Tags: quadrilateral, edges, connectivity.
        Use when: matching, comparing, or exporting quadrilateral face edges.
        Returns:
            list: Four ``[start_node, end_node]`` edge pairs.
        """
        return [
            [self.nodes[0], self.nodes[1]],
            [self.nodes[1], self.nodes[2]],
            [self.nodes[2], self.nodes[3]],
            [self.nodes[3], self.nodes[0]]
        ]

    @property
    def edge_vectors(self):
        """Return coordinate vectors for each quadrilateral edge.

        Category: mesh geometry.
        Tags: quadrilateral, edges, vectors, coordinates.
        Use when: computing lengths, normals, or geometric checks for a
            quadrilateral face.
        Returns:
            list: Four vectors following the face edge order.
        """
        return [
            self.coords[1] - self.coords[0],
            self.coords[2] - self.coords[1],
            self.coords[3] - self.coords[2],
            self.coords[0] - self.coords[3],
        ]
