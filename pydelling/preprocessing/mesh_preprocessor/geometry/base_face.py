"""
Module documentation.


"""

from pydelling.readers.iGPReader.utils.geometry_utils import *
from pydelling.utils.geometry import Plane
from .base_abstract_mesh_object import BaseAbstractMeshObject


class BaseFace(BaseAbstractMeshObject):
    """Base geometry object for mesh element faces.

    Category: preprocessing
    Tags: mesh, face, geometry, area, plane
    Use when: implementing triangular or quadrilateral faces used by mesh elements and intersections.
    """
    _local_id = 0
    __slots__ = ['node_ids', 'node_coords']
    def __init__(self, node_ids, node_coords, face_id=None):
        """Initialize a face from node ids and coordinates.

        Category: preprocessing
        Tags: mesh, face, nodes, coordinates
        Use when: concrete face classes need shared state for geometry operations.

        Returns:
            None: stores nodes, coordinates, ids, and face metadata.
        """
        self.nodes = np.array(node_ids)
        self.coords = np.array(node_coords)
        self.n_coords = len(node_coords)
        self.type = 'BaseFace'
        # self.local_id = BaseFace.local_id
        # BaseFace.local_id += 1
        self.id = BaseFace._local_id
        self.local_id = BaseFace._local_id
        self.face_id = face_id
        BaseFace._local_id += 1

    @property
    def area(self):
        """Return the face area.

        Category: preprocessing
        Tags: mesh, face, area, geometry
        Use when: mesh connection and boundary export routines need face areas.

        Returns:
            float: computed face area.
        """
        return self.compute_area()

    @property
    def centroid(self):
        """Return the face centroid.

        Category: preprocessing
        Tags: mesh, face, centroid, geometry
        Use when: intersections or exports need a representative face point.

        Returns:
            numpy.ndarray: centroid coordinates.
        """
        return self.compute_centroid()

    @property
    def n_nodes(self):
        """Return the number of nodes in the face.

        Category: preprocessing
        Tags: mesh, face, nodes, topology
        Use when: exporters need to distinguish triangular and quadrilateral faces.

        Returns:
            int: node count.
        """
        return len(self.nodes)

    def compute_area(self):
        """Compute the area of this 3D planar polygon.

        Category: preprocessing
        Tags: mesh, face, area, polygon, geometry
        Use when: mesh connection or boundary condition export needs face area.

        Returns:
            float: planar polygon area.
        """
        assert len(self.coords >= 3), "Incorrect number of points, more are needed to form a polygon"
        # Compute normal
        vn = normal_vector(self.coords)
        temp_area_v = np.zeros(shape=3)
        projected_area = 0.0
        for id, point in enumerate(self.coords):
            # Set-up variables
            v1 = self.coords[id % self.n_coords]  # Pv1, assuming P=(0,0,0)
            v2 = self.coords[(id + 1) % self.n_coords]  # Pv2, assuming P=(0,0,0)
            # Compute area
            id_area_v = np.cross(v1, v2)
            projected_area_id = np.dot(vn, id_area_v) / 2.0  # area of small triangle of the face
            projected_area += projected_area_id
        return projected_area

    def compute_centroid(self):
        """Compute the mean coordinate centroid of the face.

        Category: preprocessing
        Tags: mesh, face, centroid, geometry
        Use when: scripts need a simple centroid estimate from face coordinates.

        Returns:
            numpy.ndarray: mean coordinate centroid.
        """
        return np.mean(self.coords, axis=0)

    def compute_centroid_mean(self):
        """Compute the mean coordinate centroid of the face.

        Category: preprocessing
        Tags: mesh, face, centroid, mean, geometry
        Use when: callers explicitly want mean-based centroid calculation.

        Returns:
            numpy.ndarray: mean coordinate centroid.
        """
        return np.mean(self.coords, axis=0)

    def plot_face(self):
        """Plot this face and centroid points in 3D.

        Category: preprocessing
        Tags: mesh, face, plot, debug, geometry
        Use when: interactively debugging face coordinates or centroid placement.

        Returns:
            None: shows a matplotlib 3D plot.
        """
        from mpl_toolkits.mplot3d import Axes3D
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        import matplotlib.pyplot as plt
        x = []
        y = []
        z = []
        # points = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 1.0]]
        for point in self.coords:
            x.append(point[0])
            y.append(point[1])
            z.append(point[2])
        fig = plt.figure()
        ax = Axes3D(fig)
        verts = [list(zip(x, y, z))]
        c_mean = np.mean(self.coords, axis=0)
        ax.scatter3D(xs=[self.centroid[0]], ys=[self.centroid[1]], zs=[self.centroid[2]], c="r")
        ax.scatter3D(xs=[c_mean[0]], ys=[c_mean[1]], zs=[c_mean[2]], c="g")
        ax.add_collection3d(Poly3DCollection(verts, alpha=0.5))
        ax.axes.set_xlim3d(np.min(self.coords[:, 0]), np.max(self.coords[:, 0]))
        ax.axes.set_ylim3d(np.min(self.coords[:, 1]), np.max(self.coords[:, 1]))
        ax.axes.set_zlim3d(np.min(self.coords[:, 2]), np.max(self.coords[:, 2]))
        plt.show()

    def intersect_with_plane(self, plane: Plane):
        """Intersect this face plane with another plane.

        Category: preprocessing
        Tags: mesh, face, plane, intersection, geometry
        Use when: element-plane or fracture-plane workflows need face intersection lines.

        Returns:
            Any: result returned by Plane.intersect.
        """
        return self.plane.intersect(plane)

    @property
    def unit_normal_vector(self):
        """Return the face unit normal vector.

        Category: preprocessing
        Tags: mesh, face, normal, geometry
        Use when: containment, plane construction, or connection calculations need face orientation.

        Returns:
            numpy.ndarray: unit normal vector.
        """
        if not hasattr(self, '_unit_normal_vector'):
            v1 = self.coords[1] - self.coords[0]
            v2 = self.coords[2] - self.coords[0]
            self._unit_normal_vector = np.cross(v1, v2) / np.linalg.norm(np.cross(v1, v2))

        return self._unit_normal_vector

    @property
    def edges(self):
        """Return the face edge connectivity.

        Category: preprocessing
        Tags: mesh, face, edges, topology
        Use when: concrete face subclasses expose local edge node pairs.

        Returns:
            NotImplementedError: base class does not implement edge connectivity.
        """
        return NotImplementedError('This method is not implemented yet')

    @property
    def edge_vectors(self):
        """Return geometric edge vectors for this face.

        Category: preprocessing
        Tags: mesh, face, edge-vectors, geometry
        Use when: concrete face subclasses expose directed edge vectors for intersections.

        Returns:
            NotImplementedError: base class does not implement edge vectors.
        """
        return NotImplementedError('This method is not implemented yet')


    @property
    def plane(self):
        """Return the geometric plane containing this face.

        Category: preprocessing
        Tags: mesh, face, plane, normal, geometry
        Use when: face-plane intersections or containment checks need a Plane object.

        Returns:
            Plane: plane through the centroid with this face normal.
        """
        return Plane(self.centroid, normal=self.unit_normal_vector)

    def __repr__(self):
        return f"{self.type}-{self.local_id}"

    def __eq__(self, other):
        """Compare faces by node ids.

        Category: util
        Tags: mesh, face, equality, topology
        Use when: scripts need to test whether two BaseFace instances refer to the same node ordering.

        Returns:
            bool: True when other is a BaseFace with identical nodes.
        """
        if isinstance(other, BaseFace):
            return np.all(self.nodes == other.nodes)
        else:
            return False
