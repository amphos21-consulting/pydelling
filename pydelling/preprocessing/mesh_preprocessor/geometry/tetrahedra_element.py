"""
Module documentation.


"""

import numpy as np

from pydelling.preprocessing.mesh_preprocessor.geometry import TriangleFace, BaseElement


class TetrahedraElement(BaseElement):
    """Mesh-preprocessor tetrahedra element with meshio metadata.

    Category: mesh geometry.
    Tags: tetrahedra, element, meshio, faces, centroid.
    Use when: to understand the mesh-preprocessor representation of
        tetrahedral cells.
    """

    def __init__(self, node_ids, node_coords, centroid_coords=None, local_id=None):
        """Create a tetrahedra element from node ids and coordinates.

        Category: mesh geometry.
        Tags: tetrahedra, element, nodes, centroid.
        Use when: storing tetrahedral topology in the mesh preprocessor.
        Args:
            node_ids: Four node ids defining the element.
            node_coords: Coordinates for each node.
            centroid_coords: Optional precomputed centroid coordinates.
            local_id: Optional local element id.
        Side effects:
            Sets element type, meshio type, centroid, and centroid coordinates.
        """
        super().__init__(node_ids=node_ids, node_coords=node_coords, centroid_coords=centroid_coords, local_id=local_id)
        self.type = "tetrahedra"
        self.meshio_type = "tetra"

        if centroid_coords is None:
            self.centroid = self.compute_centroid()
            self.centroid_coords = self.centroid
        else:
            self.centroid = np.array(centroid_coords)
            self.centroid_coords = self.centroid

    def define_faces(self):
        # Add faces that define the wedge
        """Populate tetrahedra face definitions.

        Category: mesh geometry.
        Tags: tetrahedra, faces, triangle.
        Use when: face topology is needed for connection or boundary
            operations.
        Side effects:
            Adds four triangular faces to ``self.faces``.
        """
        # Face 1
        self.faces["t1"] = TriangleFace(node_ids=np.array([self.nodes[0],
                                                           self.nodes[1],
                                                           self.nodes[3]]),
                                        node_coords=np.array([self.coords[0],
                                                              self.coords[1],
                                                              self.coords[3]]),
                                        face_id="t1"
                                        )

        # Face 2
        self.faces["t2"] = TriangleFace(node_ids=np.array([self.nodes[1],
                                                           self.nodes[2],
                                                           self.nodes[3]]),
                                        node_coords=np.array([self.coords[1],
                                                              self.coords[2],
                                                              self.coords[3]]),
                                        face_id="t2"
                                        )
        # Face 3
        self.faces["t3"] = TriangleFace(node_ids=np.array([self.nodes[0],
                                                           self.nodes[3],
                                                           self.nodes[2]]),
                                        node_coords=np.array([self.coords[0],
                                                              self.coords[3],
                                                              self.coords[2]]),
                                        face_id="t3"
                                        )
        # Face 4
        self.faces["t4"] = TriangleFace(node_ids=np.array([self.nodes[0],
                                                           self.nodes[2],
                                                           self.nodes[1]]),
                                        node_coords=np.array([self.coords[0],
                                                              self.coords[2],
                                                              self.coords[1]]),
                                        face_id="t4"
                                        )
    @property
    def local_face_nodes(self):
        """Return local node indices for each tetrahedra face.

        Category: mesh geometry.
        Tags: tetrahedra, faces, local-nodes.
        Use when: exporting or comparing tetrahedral face topology.
        Returns:
            dict: Face id to local node index list.
        """
        return {
            't1': [0, 1, 3],
            't2': [1, 2, 3],
            't3': [0, 3, 2],
            't4': [0, 2, 1]
        }


