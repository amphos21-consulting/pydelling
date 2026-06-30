"""
Module documentation.


"""

from scipy.spatial.qhull import ConvexHull

from pydelling.preprocessing.mesh_preprocessor.geometry import BaseElement, TriangleFace, QuadrilateralFace
from pydelling.readers.iGPReader.utils.geometry_utils import *


class WedgeElement(BaseElement):
    """Mesh-preprocessor wedge element with meshio metadata.

    Category: mesh geometry.
    Tags: wedge, element, meshio, faces, centroid.
    Usage: to understand the mesh-preprocessor representation of wedge
        cells imported from meshio or generated internally.
    """

    def __init__(self, node_ids, node_coords, centroid_coords=None, local_id=None):
        """Create a wedge element from node ids and coordinates.

        Category: mesh geometry.
        Tags: wedge, element, nodes, centroid.
        Usage: storing wedge topology in the mesh preprocessor.
        Args:
            node_ids: Six node ids defining the wedge.
            node_coords: Coordinates for each node.
            centroid_coords: Optional precomputed centroid coordinates.
            local_id: Optional local element id.
        Side effects:
            Sets element type, meshio type, centroid, and centroid coordinates.
        """
        super().__init__(node_ids=node_ids, node_coords=node_coords, centroid_coords=centroid_coords, local_id=local_id)
        self.type = "wedge"
        self.meshio_type = "wedge"  # TODO:Check in meshio documentation

        if centroid_coords is None:
            self.centroid = self.compute_centroid()
            self.centroid_coords = self.centroid
        else:
            self.centroid = np.array(centroid_coords)
            self.centroid_coords = self.centroid

    def define_faces(self):
        # Add faces that define the wedge
        """Populate wedge face definitions.

        Category: mesh geometry.
        Tags: wedge, faces, quadrilateral, triangle.
        Usage: face topology is needed for connection or boundary
            operations.
        Side effects:
            Adds three quadrilateral and two triangular faces to ``self.faces``.
        """
        # Face 1
        self.faces["q1"] = QuadrilateralFace(node_ids=np.array([self.nodes[0],
                                                                self.nodes[1],
                                                                self.nodes[4],
                                                                self.nodes[3]]),
                                             node_coords=np.array([self.coords[0],
                                                                   self.coords[1],
                                                                   self.coords[4],
                                                                   self.coords[3]],),
                                             face_id="q1",
                                             )


        # Face 2
        self.faces["q2"] = QuadrilateralFace(node_ids=np.array([self.nodes[1],
                                                                self.nodes[2],
                                                                self.nodes[5],
                                                                self.nodes[4]]),
                                             node_coords=np.array([self.coords[1],
                                                                   self.coords[2],
                                                                   self.coords[5],
                                                                   self.coords[4]]),
                                             face_id="q2",
                                             )
        # Face 3
        self.faces["q3"] = QuadrilateralFace(node_ids=np.array([self.nodes[2],
                                                                self.nodes[0],
                                                                self.nodes[3],
                                                                self.nodes[5]]),
                                             node_coords=np.array([self.coords[2],
                                                                   self.coords[0],
                                                                   self.coords[3],
                                                                   self.coords[5]]),
                                             face_id="q3",
                                             )
        # Face 4
        self.faces["t1"] = TriangleFace(node_ids=np.array([self.nodes[0],
                                                           self.nodes[2],
                                                           self.nodes[1]]),
                                        node_coords=np.array([self.coords[0],
                                                              self.coords[2],
                                                              self.coords[1]]),
                                        face_id="t1",
                                        )
        # Face 5
        self.faces["t2"] = TriangleFace(node_ids=np.array([self.nodes[3],
                                                           self.nodes[4],
                                                           self.nodes[5]]),
                                        node_coords=np.array([self.coords[3],
                                                              self.coords[4],
                                                              self.coords[5]]),
                                        face_id="t2",
                                        )
    @property
    def local_face_nodes(self):
        """Return local node indices for each wedge face.

        Category: mesh geometry.
        Tags: wedge, faces, local-nodes.
        Usage: exporting or comparing wedge face topology.
        Returns:
            dict: Face id to local node index list.
        """
        return {
            'q1': [0, 1, 4, 3],
            'q2': [1, 2, 5, 4],
            'q3': [2, 0, 3, 5],
            't1': [0, 2, 1],
            't2': [3, 4, 5]
        }
