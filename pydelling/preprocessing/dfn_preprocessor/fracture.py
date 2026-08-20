"""
Module documentation.


"""

from typing import List

import numpy as np
import shapely.geometry as geom

from pydelling.utils.geometry import Plane, Segment, Point, Line


class Fracture(object):
    """Represent a rectangular or polygonal DFN fracture with hydraulic properties.

    Category: preprocessing
    Tags: dfn, fracture, geometry, aperture, transmissivity
    Usage: scripts need fracture geometry, containment checks, or hydraulic properties for DFN upscaling.
    """
    local_id = 0
    eps = 1e-3
    _transmissivity = None
    _storativity = None
    _side_points = None
    _unit_normal_vector = None

    def __init__(
        self,
        x=None,
        y=None,
        z=None,
        dip=None,
        dip_dir=None,
        size=None,
        aperture=None,
        hydraulic_aperture=None,
        transmissivity=None,
        storativity=None,
        rock_type=None,
        aperture_constant=None,
        transmissivity_constant=None,
        storativity_constant=None,
        normal_vector=None,
        polygon: List[np.ndarray] = None,
        effective_aperture=None,
        porosity=None,
        hydraulic_conductivity=None,
        specific_storage=None,
    ):
        """Initialize fracture geometry and optional hydraulic constants.

        Category: preprocessing
        Tags: dfn, fracture, geometry, aperture, rock-type
        Usage: scripts need a fracture from centroid/dip/size inputs or explicit polygon points.

        Returns:
            None: stores geometry, hydraulic fields, side points, and local id.
        """
        self._transmissivity = transmissivity
        self._storativity = storativity
        self._plane = None
        self._corners = None
        self._polygon = None
        self._side_points = None
        self._unit_normal_vector = None
        if normal_vector is not None:
            self._unit_normal_vector: np.ndarray = normal_vector
        self.side_points = None
        if dip is not None:
            assert dip_dir is not None
        if polygon is None and size is None:
            raise ValueError("a generated fracture requires size; polygon fractures do not")
        # Allow definition of a Fracture object based on a polygon
        if polygon is not None:
            # Assert x, y, z are not provided
            self._side_points = polygon
            centroid = np.mean(polygon, axis=0)
            x = centroid[0]
            y = centroid[1]
            z = centroid[2]
        self.polygon_points = polygon

        self.dip = dip
        self.dip_dir = dip_dir
        self.x_centroid = x
        self.y_centroid = y
        self.z_centroid = z
        self.size = size
        self._aperture = aperture
        self.hydraulic_aperture = hydraulic_aperture
        self.effective_aperture = effective_aperture
        self.porosity = porosity
        self.hydraulic_conductivity = hydraulic_conductivity
        self.specific_storage = specific_storage
        self.rock_type = rock_type
        self.intersection_dictionary = {}
        self.aperture_constant = aperture_constant
        if transmissivity_constant is not None:
            if rock_type is not None:
                if isinstance(transmissivity_constant, dict):
                    self.transmissivity_constant = transmissivity_constant[
                        int(rock_type)
                    ]
                else:
                    self.transmissivity_constant = transmissivity_constant
            else:
                self.transmissivity_constant = transmissivity_constant
        else:
            self.transmissivity_constant = None
        if storativity_constant is not None:
            if rock_type is not None:
                if isinstance(storativity_constant, dict):
                    self.storativity_constant = storativity_constant[int(rock_type)]
                else:
                    self.storativity_constant = storativity_constant
            else:
                self.storativity_constant = storativity_constant
        else:
            self.storativity_constant = None

        self.aperture = self.compute_aperture()
        self.local_id = Fracture.local_id
        self.side_points = self.get_side_points()
        self.n_side_points = len(self.side_points)

        Fracture.local_id += 1

    def get_side_points_v1(self):
        """Compute rectangular fracture corners with the v1 orientation formula.

        Category: preprocessing
        Tags: dfn, fracture, corners, dip, geometry
        Usage: generating side points from dip, dip direction, centroid, and size.

        Returns:
            numpy.ndarray: four corner coordinates.
        """
        phi = self.dip_dir / 360 * (2 * np.pi)
        theta = self.dip / 360 * (2 * np.pi)

        u = np.array(
            [np.cos(theta) * np.sin(phi), np.cos(theta) * np.cos(phi), -np.sin(theta)]
        )
        v = np.array([np.cos(phi), -np.sin(phi), 0])

        A = self.centroid + self.size / 2 * (u + v)
        B = self.centroid + self.size / 2 * (u - v)
        C = self.centroid - self.size / 2 * (u + v)
        D = self.centroid - self.size / 2 * (u - v)

        self.side_points = 4

        return np.array([A, B, C, D])

    def get_side_points_v3(self):
        """Compute rectangular fracture corners with the v3 strike/dip formula.

        Category: preprocessing
        Tags: dfn, fracture, corners, strike, dip
        Usage: legacy workflows need the v3 corner construction for a square fracture.

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
        C = (
            np.array(
                [
                    L * np.cos(np.pi / 2 - alpha) + H,
                    L * np.sin(np.pi / 2 - alpha) + V,
                    Z,
                ]
            )
            + A
        )
        D = (
            np.array(
                [
                    w * np.sin(alpha + np.pi / 2),
                    w * np.cos(alpha + np.pi / 2),
                    -w * np.sin(delta),
                ]
            )
            + A
        )

        P = np.array([A, B, C, D])

        return P

    def get_side_points_v2(self):
        """Compute rectangular fracture corners with the v2 orientation formula.

        Category: preprocessing
        Tags: dfn, fracture, corners, dip, geometry
        Usage: scripts need the alternate dip/dip-direction corner construction.

        Returns:
            numpy.ndarray: four corner coordinates.
        """
        alpha = self.dip / 360 * (2 * np.pi)
        beta = self.dip_dir / 360 * (2 * np.pi)

        A = self.centroid + np.array(
            [
                +self.size / 2 * (-np.cos(beta) - np.sin(beta) * np.cos(alpha)),
                +self.size / 2 * (np.sin(beta) - np.cos(beta) * np.cos(alpha)),
                self.size / 2 * np.sin(alpha),
            ]
        )

        B = self.centroid + np.array(
            [
                +self.size / 2 * (-np.cos(beta) + np.sin(beta) * np.cos(alpha)),
                +self.size / 2 * (np.sin(beta) + np.cos(beta) * np.cos(alpha)),
                -self.size / 2 * np.sin(alpha),
            ]
        )

        C = self.centroid + np.array(
            [
                +self.size / 2 * (np.cos(beta) + np.sin(beta) * np.cos(alpha)),
                +self.size / 2 * (-np.sin(beta) + np.cos(beta) * np.cos(alpha)),
                -self.size / 2 * np.sin(alpha),
            ]
        )

        D = self.centroid + np.array(
            [
                +self.size / 2 * (np.cos(beta) - np.sin(beta) * np.cos(alpha)),
                +self.size / 2 * (-np.sin(beta) - np.cos(beta) * np.cos(alpha)),
                +self.size / 2 * np.sin(alpha),
            ]
        )

        self.side_points = 4

        return np.array([A, B, C, D])

    def get_side_points(self, method="v1"):
        """Return fracture side points using an explicit polygon or a construction method.

        Category: preprocessing
        Tags: dfn, fracture, corners, polygon, geometry
        Usage: intersection and export routines need fracture corner coordinates.

        Returns:
            numpy.ndarray: fracture side point coordinates.
        """
        if self._side_points is not None:
            return self._side_points
        if method == "v1":
            return self.get_side_points_v1()
        elif method == "v2":
            return self.get_side_points_v2()
        elif method == "v3":
            return self.get_side_points_v3()

    def to_obj(self, global_id=0, method="v1"):
        """Return this fracture polygon as Wavefront OBJ text.

        Category: writer
        Tags: dfn, fracture, obj, export, geometry
        Usage: scripts need a simple visual-debug representation of one fracture.

        Returns:
            str: OBJ vertex and face records.
        """
        side_points = self.get_side_points(method=method)
        if isinstance(side_points[0], np.ndarray):
            side_points = [side_point.tolist() for side_point in side_points]
        obj_string = ""
        for i in range(len(side_points)):
            obj_string += (
                "v "
                + str(side_points[i][0])
                + " "
                + str(side_points[i][1])
                + " "
                + str(side_points[i][2])
                + "\n"
            )
        obj_string += f"f "
        for i in range(len(side_points)):
            obj_string += str(global_id + i) + " "
        obj_string += "\n"
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
        if self._unit_normal_vector is None:
            get_side_points = self.get_side_points()
            v1 = get_side_points[1] - get_side_points[0]
            v2 = get_side_points[2] - get_side_points[0]
            cross = np.cross(v1, v2)
            self._unit_normal_vector = cross / np.linalg.norm(cross)
        return self._unit_normal_vector

    def distance_to_point(self, point: np.ndarray):
        """Compute perpendicular distance from a point to the fracture plane.

        Category: preprocessing
        Tags: dfn, fracture, distance, point, plane
        Usage: containment checks or mesh-fracture filtering need point-to-plane distance.

        Returns:
            float: absolute distance to the fracture plane.
        """
        a = self.unit_normal_vector[0]
        b = self.unit_normal_vector[1]
        c = self.unit_normal_vector[2]
        d = -np.dot(self.unit_normal_vector, self.centroid)
        return abs(a * point[0] + b * point[1] + c * point[2] + d) / np.sqrt(
            a**2 + b**2 + c**2
        )

    def get_bounding_box(self):
        """Return the axis-aligned bounding box of the fracture.

        Category: preprocessing
        Tags: dfn, fracture, bounding-box, geometry
        Usage: scripts need quick spatial filtering before exact intersection checks.

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

    def point_inside_bounding_box(self, point: np.ndarray, scale_factor=0.0):
        """Check whether a point lies inside the fracture bounding box.

        Category: preprocessing
        Tags: dfn, fracture, bounding-box, point, filter
        Usage: scripts need a fast pre-check before fracture polygon containment.

        Returns:
            bool: True when the point is inside the scaled bounding box.
        """
        bounding_box = self.get_bounding_box()
        lx = bounding_box[1] - bounding_box[0]
        ly = bounding_box[3] - bounding_box[2]
        lz = bounding_box[5] - bounding_box[4]

        if (
            point[0] < bounding_box[0] - scale_factor * lx
            or point[0] > bounding_box[1] + scale_factor * lx
        ):
            return False
        if (
            point[1] < bounding_box[2] - scale_factor * ly
            or point[1] > bounding_box[3] + scale_factor * ly
        ):
            return False
        if (
            point[2] < bounding_box[4] - scale_factor * lz
            or point[2] > bounding_box[5] + scale_factor * lz
        ):
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
        Usage: scripts need polygon operations on the fracture side points.

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
        if self._plane is None:
            self._plane = Plane(self.centroid, normal=self.unit_normal_vector)

        return self._plane

    @property
    def corners(self) -> List[Point]:
        """Return fracture corners as Point objects.

        Category: preprocessing
        Tags: dfn, fracture, corners, points, geometry
        Usage: intersection routines need corner objects instead of raw arrays.

        Returns:
            list: Point objects for each corner.
        """
        if self._corners is None:
            self._corners = [Point(point) for point in self.get_side_points()]
        return self._corners

    @property
    def corner_segments(self):
        """Return fracture boundary edges as Segment objects.

        Category: preprocessing
        Tags: dfn, fracture, segments, boundary, geometry
        Usage: scripts need finite fracture edges for geometric intersection checks.

        Returns:
            list: Segment objects around the fracture boundary.
        """
        return [
            Segment(self.corners[index], self.corners[(index + 1) % len(self.corners)])
            for index in range(len(self.corners))
        ]

    @property
    def corner_lines(self):
        """Return fracture boundary edges as Line objects.

        Category: preprocessing
        Tags: dfn, fracture, lines, boundary, geometry
        Usage: element intersection routines need fracture edge-line intersections.

        Returns:
            list: Line objects around the fracture boundary.
        """
        return [
            Line(self.corners[index], self.corners[(index + 1) % len(self.corners)])
            for index in range(len(self.corners))
        ]

    def contains(self, point: np.ndarray) -> bool:
        """Check whether a 3D point lies inside the fracture polygon.

        Category: preprocessing
        Tags: dfn, fracture, contains, point, polygon
        Usage: mesh-fracture intersection routines need to filter candidate points.

        Returns:
            bool: True when the point is on the fracture plane and inside its polygon.
        """
        # Step 1: Check if the point is close to the fracture's plane
        distance = self.distance_to_point(point)
        if distance > self.eps:
            return False  # The point is not on the fracture's plane

        # Step 2: Project the polygon and the point onto a 2D plane
        normal = self.unit_normal_vector
        largest_index = np.argmax(np.abs(normal))  # Choose the projection plane
        # Indices of the two coordinates to keep
        proj_indices = [i for i in range(3) if i != largest_index]

        # Project polygon points
        projected_polygon = [p[proj_indices] for p in self.get_side_points()]
        # Ensure the polygon is closed by appending the first point at the end
        if not np.array_equal(projected_polygon[0], projected_polygon[-1]):
            projected_polygon.append(projected_polygon[0])

        # Project the point
        px, py = point[proj_indices]

        # Step 3: Perform the Ray Casting algorithm
        num_intersections = 0
        num_vertices = len(projected_polygon)

        for i in range(num_vertices - 1):
            x1, y1 = projected_polygon[i]
            x2, y2 = projected_polygon[i + 1]

            # Check if the point is exactly on a vertex
            if (px == x1 and py == y1) or (px == x2 and py == y2):
                return True  # Consider the point as inside

            # Check if the point is on the edge
            if self._point_on_segment(px, py, x1, y1, x2, y2):
                return True  # Consider the point as inside

            # Check if the edge intersects with the ray
            # Conditions:
            # 1. The y-coordinate of the point is between the y-coordinates of the edge's endpoints
            # 2. The point is to the left of the edge
            if (y1 > py) != (y2 > py):
                # Compute the x-coordinate of the intersection point
                x_intersect = (x2 - x1) * (py - y1) / (y2 - y1 + 1e-12) + x1
                if px < x_intersect:
                    num_intersections += 1

        # If the number of intersections is odd, the point is inside
        return num_intersections % 2 == 1

    def _point_on_segment(self, px, py, x1, y1, x2, y2) -> bool:
        """Check whether a projected point lies on a projected segment.

        Returns:
            bool: True when the point lies on the segment within tolerance.

        Category: util
        Tags: dfn, fracture, segment, containment, geometry
        Usage: contains needs to treat boundary points as inside the fracture polygon.
        """
        # Check if the point is within the bounding box of the segment
        if (
            min(x1, x2) - self.eps <= px <= max(x1, x2) + self.eps
            and min(y1, y2) - self.eps <= py <= max(y1, y2) + self.eps
        ):
            # Compute the cross product to check collinearity
            dx = x2 - x1
            dy = y2 - y1
            if abs(dx) < self.eps and abs(dy) < self.eps:
                # The segment is a point
                return abs(px - x1) < self.eps and abs(py - y1) < self.eps
            elif abs(dx) < self.eps:
                # Vertical segment
                return abs(px - x1) < self.eps
            elif abs(dy) < self.eps:
                # Horizontal segment
                return abs(py - y1) < self.eps
            else:
                # General case
                slope = dy / dx
                expected_py = slope * (px - x1) + y1
                return abs(py - expected_py) < self.eps
        return False

    def shift(self, x, y, z):
        """Translate the fracture by x, y, and z offsets.

        Category: preprocessing
        Tags: dfn, fracture, translate, geometry
        Usage: scripts need to move a fracture while preserving its shape and properties.

        Returns:
            None: updates centroid fields and polygon side points.
        """
        self.x_centroid += x
        self.y_centroid += y
        self.z_centroid += z
        if self._side_points is not None:
            self._side_points = [
                point + np.array([x, y, z]) for point in self._side_points
            ]
        self._plane = None
        self._corners = None
        self._polygon = None

    @property
    def area(self):
        """Return the area of an arbitrary planar fracture polygon."""

        points = np.asarray(self.get_side_points(), dtype=float)
        if len(points) < 3:
            return 0.0
        normal = self.unit_normal_vector
        return abs(float(np.dot(np.sum(np.cross(points, np.roll(points, -1, axis=0)), axis=0), normal))) * 0.5

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

    def compute_aperture(self, const=3.020e-3):
        """Compute or return the fracture mechanical aperture.

        Category: preprocessing
        Tags: dfn, fracture, aperture, hydraulic, size
        Usage: scripts need fracture aperture from explicit input or an aperture-size law.

        Returns:
            float: fracture aperture.
        """
        if self._aperture is not None:
            return self._aperture
        elif self.aperture_constant is not None and self.size is not None:
            # const = config.globals.constants
            # computed_aperture = np.power((12 * const.mu
            #                              * config.globals.constitutive_laws.transmissivity.a
            #                              * np.log10(self.size / 2.0) ** 2) / (const.rho * const.g), 1/3)
            computed_aperture = self.aperture_constant * np.log10(self.size / 2.0)
            return computed_aperture
        return None

    @property
    def transmissivity(self):
        """Return fracture transmissivity.

        Category: preprocessing
        Tags: dfn, fracture, transmissivity, hydraulic, aperture
        Usage: DFN upscaling needs transmissivity from explicit input, constants, or hydraulic aperture.

        Returns:
            float: fracture transmissivity.
        """
        if self._transmissivity is not None:
            return self._transmissivity
        elif self.transmissivity_constant is not None:
            computed_transmissivity = (
                self.transmissivity_constant * (np.log10(self.size / 2.0)) ** 2
            )
            return computed_transmissivity
        else:
            rho = 1000
            g = 9.8
            mu = 8.9e-4
            return (np.power(self.hydraulic_aperture, 3) * rho * g) / (12 * mu)

    @property
    def storativity(self):
        """Return fracture storativity.

        Category: preprocessing
        Tags: dfn, fracture, storativity, hydraulic
        Usage: DFN upscaling needs per-fracture storativity values.

        Returns:
            float: fracture storativity.
        """
        if self._storativity is not None:
            return self._storativity
        elif self.storativity_constant is not None:
            computed_storativity = self.storativity_constant * np.log10(self.size / 2.0)
            return computed_storativity
        else:
            return 0.0

    def get_json(self):
        """Build a JSON-serializable fracture metadata dictionary.

        Category: writer
        Tags: dfn, fracture, json, serialize, geometry
        Usage: scripts need to persist fracture geometry and hydraulic constants.

        Returns:
            dict: serializable fracture metadata.
        """
        cur_dict = {
            "x": self.x_centroid,
            "y": self.y_centroid,
            "z": self.z_centroid,
            "size": self.size,
            "aperture": self.aperture,
            "dip": self.dip,
            "dip_dir": self.dip_dir,
            "aperture_constant": self.aperture_constant,
            "rock_type": self.rock_type,
            "transmissivity_constant": self.transmissivity_constant,
            "storativity_constant": self.storativity_constant,
            "transmissivity": self._transmissivity,
            "storativity": self._storativity,
            "effective_aperture": self.effective_aperture,
            "porosity": self.porosity,
            "hydraulic_conductivity": self.hydraulic_conductivity,
            "specific_storage": self.specific_storage,
            "normal_vector": self._unit_normal_vector.tolist()
            if self._unit_normal_vector is not None
            else None,
            "polygon": [point.tolist() for point in self.polygon_points]
            if self.polygon_points is not None
            else None,
        }

        return cur_dict
