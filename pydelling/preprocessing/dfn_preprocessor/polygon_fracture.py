"""
Module documentation.


"""

from typing import List

import numpy as np
import shapely.geometry as geom

from pydelling.utils.geometry import Plane, Segment, Point, Line


class PolygonFracture:
    """Represent a legacy rectangular polygon fracture.

    Category: preprocessing
    Tags: dfn, fracture, polygon, geometry, legacy
    Usage: scripts need the older polygon-fracture geometry helpers for DFN intersection workflows.
    """
    local_id = 0
    eps = 1e-8
    def __init__(self, dip, dip_dir, x, y, z, size, aperture=0.01):
        # super().__init__(dip, dip_dir, x, y, z, size, aperture)
        """Initialize a polygon fracture from orientation, centroid, and size.

        Category: preprocessing
        Tags: dfn, fracture, polygon, dip, aperture
        Usage: legacy scripts need a rectangular fracture object with geometric helpers.

        Returns:
            None: stores geometry, aperture, and local id.
        """
        self.side_points = None
        self.dip = dip
        self.dip_dir = dip_dir
        self.x_centroid = x
        self.y_centroid = y
        self.z_centroid = z
        self.size = size
        self.intersection_dictionary = {}
        self.aperture = aperture
        self.local_id = PolygonFracture.local_id
        PolygonFracture.local_id += 1

    def get_side_points_v1(self):
        """Compute fracture corners with the v1 orientation formula.

        Category: preprocessing
        Tags: dfn, fracture, corners, dip, geometry
        Usage: generating side points from dip, dip direction, centroid, and size.

        Returns:
            numpy.ndarray: four corner coordinates.
        """
        phi = self.dip_dir / 360 * (2 * np.pi)
        theta = self.dip / 360 * (2 * np.pi)

        u = np.array([np.cos(theta) * np.sin(phi), np.cos(theta) * np.cos(phi), -np.sin(theta)])
        v = np.array([np.cos(phi), - np.sin(phi), 0])

        A = self.centroid + self.size / 2 * (u + v)
        B = self.centroid + self.size / 2 * (u - v)
        C = self.centroid - self.size / 2 * (u + v)
        D = self.centroid - self.size / 2 * (u - v)


        self.side_points = 4

        return np.array([A, B, C, D])


    def get_side_points_v3(self):
        """Compute fracture corners with the v3 strike/dip formula.

        Category: preprocessing
        Tags: dfn, fracture, corners, strike, dip
        Usage: legacy workflows need the alternate v3 square-fracture construction.

        Returns:
            numpy.ndarray: four corner coordinates.
        """
        alpha = self.dip_dir / 360 * (2 * np.pi)
        delta = self.dip / 360 * (2 * np.pi)
        w = self.size
        L = self.size

        A = np.array(self.centroid)
        A[0] = A[0] - np.sin(alpha) * L / 2
        A[1] = A[1] + np.cos(alpha) * L / 2
        A[2] = A[2] + np.sin(delta) * L / 2


        H = w * np.sin(alpha + np.pi / 2)
        V = w * np.cos(alpha + np.pi / 2)
        Z = -w * np.sin(delta)

        B = np.array([L * np.sin(alpha), L * np.cos(alpha), 0]) + A
        C = np.array([L * np.cos(np.pi / 2 - alpha) + H, L * np.sin(np.pi / 2 - alpha) + V, Z]) + A
        D = np.array([w * np.sin(alpha + np.pi / 2), w * np.cos(alpha + np.pi / 2), -w * np.sin(delta)]) + A

        P = np.array([A, B, C, D])

        return P

    def get_side_points_v2(self):
        """Compute fracture corners with the v2 orientation formula.

        Category: preprocessing
        Tags: dfn, fracture, corners, dip, geometry
        Usage: scripts need the alternate dip/dip-direction corner construction.

        Returns:
            numpy.ndarray: four corner coordinates.
        """
        alpha = self.dip / 360 * (2 * np.pi)
        beta = self.dip_dir / 360 * (2 * np.pi)

        A = self.centroid + np.array([
            + self.size / 2 * (-np.cos(beta) - np.sin(beta) * np.cos(alpha)),
            + self.size / 2 * (np.sin(beta) - np.cos(beta) * np.cos(alpha)),
            self.size / 2 * np.sin(alpha)
        ])

        B = self.centroid + np.array([
            + self.size / 2 * (-np.cos(beta) + np.sin(beta) * np.cos(alpha)),
            + self.size / 2 * (np.sin(beta) + np.cos(beta) * np.cos(alpha)),
            - self.size / 2 * np.sin(alpha)
        ])

        C = self.centroid + np.array([
            + self.size / 2 * (np.cos(beta) + np.sin(beta) * np.cos(alpha)),
            + self.size / 2 * (-np.sin(beta) + np.cos(beta) * np.cos(alpha)),
            - self.size / 2 * np.sin(alpha)
        ])

        D = self.centroid + np.array([
            + self.size / 2 * (np.cos(beta) - np.sin(beta) * np.cos(alpha)),
            + self.size / 2 * (-np.sin(beta) - np.cos(beta) * np.cos(alpha)),
            + self.size / 2 * np.sin(alpha)
        ])

        self.side_points = 4

        return np.array([A, B, C, D])


    def get_side_points(self, method='v1'):
        """Return side points using the selected corner construction method.

        Category: preprocessing
        Tags: dfn, fracture, corners, polygon, geometry
        Usage: intersection, containment, or export routines need fracture corner coordinates.

        Returns:
            numpy.ndarray: fracture side point coordinates.
        """
        if method == 'v1':
            return self.get_side_points_v1()
        elif method == 'v2':
            return self.get_side_points_v2()
        elif method == 'v3':
            return self.get_side_points_v3()


    def to_obj(self, global_id=0, method='v1'):
        """Return this fracture polygon as Wavefront OBJ text.

        Category: writer
        Tags: dfn, fracture, obj, export, geometry
        Usage: scripts need a simple visual-debug representation of the fracture.

        Returns:
            str: OBJ vertex and face records.
        """
        side_points = self.get_side_points(method=method)
        obj_string = ''
        for i in range(len(side_points)):
            obj_string += 'v ' + str(side_points[i][0]) + ' ' + str(side_points[i][1]) + ' ' + str(side_points[i][2]) + '\n'
        obj_string += f'f '
        for i in range(len(side_points)):
            obj_string += str(global_id + i) + ' '
        obj_string += '\n'
        return obj_string

    @property
    def unit_normal_vector(self):
        """Return the fracture unit normal vector.

        Category: preprocessing
        Tags: dfn, fracture, normal, orientation, geometry
        Usage: plane construction, distance checks, or intersections need fracture orientation.

        Returns:
            numpy.ndarray: unit normal vector.
        """
        get_side_points = self.get_side_points()
        v1 = get_side_points[1] - get_side_points[0]
        v2 = get_side_points[2] - get_side_points[0]
        cross = np.cross(v1, v2)
        return cross / np.linalg.norm(cross)

    def distance_to_point(self, point: np.ndarray):
        """Compute signed distance from a point to the fracture plane.

        Category: preprocessing
        Tags: dfn, fracture, distance, point, plane
        Usage: scripts need point-to-plane distance for fracture filtering.

        Returns:
            float: signed distance projected on the unit normal vector.
        """
        distance_vector = self.centroid - point
        return np.dot(distance_vector, self.unit_normal_vector)

    def get_bounding_box(self):
        """Return the axis-aligned bounding box of the fracture.

        Category: preprocessing
        Tags: dfn, fracture, bounding-box, geometry
        Usage: scripts need quick spatial filtering before exact containment checks.

        Returns:
            numpy.ndarray: x_min, x_max, y_min, y_max, z_min, z_max.
        """
        side_points = self.get_side_points()
        x_min = np.min(side_points[:, 0])
        x_max = np.max(side_points[:, 0])
        y_min = np.min(side_points[:, 1])
        y_max = np.max(side_points[:, 1])
        z_min = np.min(side_points[:, 2])
        z_max = np.max(side_points[:, 2])
        return np.array([x_min, x_max, y_min, y_max, z_min, z_max])

    def point_inside_bounding_box(self, point: np.ndarray):
        """Check whether a point lies inside the fracture bounding box.

        Category: preprocessing
        Tags: dfn, fracture, bounding-box, point, filter
        Usage: scripts need a fast pre-check before polygon containment.

        Returns:
            bool: True when the point is inside the bounding box.
        """
        bounding_box = self.get_bounding_box()
        if point[0] < bounding_box[0] or point[0] > bounding_box[1]:
            return False
        elif point[1] < bounding_box[2] or point[1] > bounding_box[3]:
            return False
        elif point[2] < bounding_box[4] or point[2] > bounding_box[5]:
            return False
        else:
            return True

    @property
    def centroid(self):
        """Return the fracture centroid coordinates.

        Category: preprocessing
        Tags: dfn, fracture, centroid, geometry
        Usage: scripts need the fracture center for distance, export, or reporting.

        Returns:
            numpy.ndarray: x, y, z centroid.
        """
        return np.array([self.x_centroid, self.y_centroid, self.z_centroid])

    @property
    def polygon(self):
        """Return the fracture as a Shapely polygon.

        Category: preprocessing
        Tags: dfn, fracture, polygon, shapely, geometry
        Usage: scripts need polygon operations on fracture side points.

        Returns:
            shapely.geometry.Polygon: polygon built from side points.
        """
        side_points = self.get_side_points()
        self._polygon = geom.Polygon(side_points)
        return self._polygon


    @property
    def plane(self):
        """Return the geometric plane containing this fracture.

        Category: preprocessing
        Tags: dfn, fracture, plane, normal, geometry
        Usage: mesh-element intersection routines need the fracture plane.

        Returns:
            Plane: plane defined by centroid and unit normal vector.
        """
        return Plane(self.centroid, normal=self.unit_normal_vector)

    @property
    def corners(self) -> List[Point]:
        """Return fracture corners as Point objects.

        Category: preprocessing
        Tags: dfn, fracture, corners, points, geometry
        Usage: intersection routines need corner objects instead of raw arrays.

        Returns:
            list: Point objects for each corner.
        """
        return [Point(point) for point in self.get_side_points()]

    @property
    def corner_segments(self):
        """Return fracture boundary edges as Segment objects.

        Category: preprocessing
        Tags: dfn, fracture, segments, boundary, geometry
        Usage: scripts need finite fracture edges for geometric intersection checks.

        Returns:
            list: Segment objects around the fracture boundary.
        """
        corner_segments = [
            Segment(self.corners[0], self.corners[1]),
            Segment(self.corners[1], self.corners[2]),
            Segment(self.corners[2], self.corners[3]),
            Segment(self.corners[3], self.corners[0])
        ]
        return corner_segments

    @property
    def corner_lines(self):
        """Return fracture boundary edges as Line objects.

        Category: preprocessing
        Tags: dfn, fracture, lines, boundary, geometry
        Usage: element intersection routines need fracture edge-line intersections.

        Returns:
            list: Line objects around the fracture boundary.
        """
        corner_segments = [
            Line(self.corners[0], self.corners[1]),
            Line(self.corners[1], self.corners[2]),
            Line(self.corners[2], self.corners[3]),
            Line(self.corners[3], self.corners[0])
        ]
        return corner_segments

    def contains(self, point: Point):
        """Check whether a point lies inside the fracture polygon.

        Category: preprocessing
        Tags: dfn, fracture, contains, point, polygon
        Usage: mesh-fracture intersection routines need to filter candidate points.

        Returns:
            bool: True when the projected point is inside the polygon.
        """
        q1, q2, q3, q4 = self.corners
        q1: Point

        largest_normal_index = self.largest_index_normal_vector
        q1_hat = np.delete(q1, largest_normal_index)
        q2_hat = np.delete(q2, largest_normal_index)
        q3_hat = np.delete(q3, largest_normal_index)
        q4_hat = np.delete(q4, largest_normal_index)
        p_hat = np.delete(point, largest_normal_index)
        u0 = p_hat[0]
        u1 = q1_hat[0]
        u2 = q2_hat[0]
        u3 = q3_hat[0]
        u4 = q4_hat[0]
        v0 = p_hat[1]
        v1 = q1_hat[1]
        v2 = q2_hat[1]
        v3 = q3_hat[1]
        v4 = q4_hat[1]


        s1 = (v1 - v2) * u0 + (u2 - u1) * v0 + v2 * u1 - u2 * v1
        s2 = (v2 - v3) * u0 + (u3 - u2) * v0 + v3 * u2 - u3 * v2
        s3 = (v3 - v4) * u0 + (u4 - u3) * v0 + v4 * u3 - u4 * v3
        s4 = (v4 - v1) * u0 + (u1 - u4) * v0 + v1 * u4 - u1 * v4

        s = np.array([s1, s2, s3, s4])

        equal_sign = np.all(s >= -self.eps) if s[0] >= -self.eps else np.all(s <= self.eps)

        if equal_sign:
            return True
        else:
            return False

    @property
    def largest_index_normal_vector(self):
        """Return the dominant coordinate index of the fracture normal.

        Category: preprocessing
        Tags: dfn, fracture, normal, projection, geometry
        Usage: containment routines need a 2D projection plane.

        Returns:
            int: index of the largest absolute normal-vector component.
        """
        return np.argmax(self.unit_normal_vector)





