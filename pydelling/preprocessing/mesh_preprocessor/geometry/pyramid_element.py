"""
Module documentation.


"""

from scipy.spatial.qhull import ConvexHull

from pydelling.preprocessing.mesh_preprocessor.geometry import BaseElement, TriangleFace, QuadrilateralFace
from pydelling.readers.iGPReader.utils.geometry_utils import *


class PyramidElement(BaseElement):
    """Mesh-preprocessor pyramid element with meshio metadata.

    Category: mesh geometry.
    Tags: pyramid, element, meshio, faces, centroid.
    Use when: an MCP agent needs the mesh-preprocessor representation of pyramid
        cells.
    """

    def __init__(self, node_ids, node_coords, centroid_coords=None, local_id=None):
        """Create a pyramid element from node ids and coordinates.

        Category: mesh geometry.
        Tags: pyramid, element, nodes, centroid.
        Use when: storing pyramid topology in the mesh preprocessor.
        Args:
            node_ids: Five node ids defining the pyramid.
            node_coords: Coordinates for each node.
            centroid_coords: Optional precomputed centroid coordinates.
            local_id: Optional local element id.
        Side effects:
            Sets element type, meshio type, centroid, and centroid coordinates.
        """
        super().__init__(node_ids=node_ids, node_coords=node_coords, centroid_coords=centroid_coords, local_id=local_id)
        self.type = "pyramid"
        self.meshio_type = "pyramid"

        if centroid_coords is None:
            self.centroid = self.compute_centroid()
            self.centroid_coords = self.centroid
        else:
            self.centroid = np.array(centroid_coords)
            self.centroid_coords = self.centroid

    def define_faces(self):
        # Add faces that define the wedge
        """Populate pyramid face definitions.

        Category: mesh geometry.
        Tags: pyramid, faces, quadrilateral, triangle.
        Use when: face topology is needed for connection or boundary
            operations.
        Side effects:
            Adds one quadrilateral and three triangular faces to ``self.faces``.
        """
        # Face 1
        self.faces["q1"] = QuadrilateralFace(node_ids=np.array([self.nodes[0],
                                                                self.nodes[1],
                                                                self.nodes[2],
                                                                self.nodes[3]]),
                                                node_coords=np.array([self.coords[0],
                                                                    self.coords[1],
                                                                    self.coords[2],
                                                                    self.coords[3]]),
                                             face_id="q1"
                                             )
        # Face 2
        self.faces['t1'] = TriangleFace(node_ids=np.array([self.nodes[0],
                                                           self.nodes[4],
                                                           self.nodes[3]]),
                                             node_coords=np.array([self.coords[0],
                                                                 self.coords[4],
                                                                 self.coords[3]]),
                                        face_id="t1"
                                        )
        # Face 3
        self.faces['t2'] = TriangleFace(node_ids=np.array([self.nodes[4],
                                                           self.nodes[2],
                                                           self.nodes[1]]),
                                                node_coords=np.array([self.coords[4],
                                                                    self.coords[2],
                                                                    self.coords[1]]),
                                        face_id="t2"
                                        )
        # Face 4
        self.faces['t3'] = TriangleFace(node_ids=np.array([self.nodes[4],
                                                          self.nodes[3],
                                                          self.nodes[2]]),
                                                node_coords=np.array([self.coords[4],
                                                                    self.coords[3],
                                                                    self.coords[2]]),
                                        face_id="t3"
                                        )



    @property
    def local_face_nodes(self):
        """Return local node indices for each pyramid face.

        Category: mesh geometry.
        Tags: pyramid, faces, local-nodes.
        Use when: exporting or comparing pyramid face topology.
        Returns:
            dict: Face id to local node index list.
        """
        return {
            'q1': [0, 1, 2, 3],
            't1': [0, 4, 3],
            't2': [4, 2, 1],
            't3': [4, 3, 2]
        }

