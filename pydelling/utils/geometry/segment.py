"""
Module documentation.


"""

import numpy as np

from . import Line, Point, BasePrimitive


class Segment(Line):
    """Finite line segment represented by two endpoint ``Point`` objects.

    Category: geometry primitive.
    Tags: segment, point, length, intersection, containment.
    Use when: to use bounded line geometry for mesh, polygon, or
        plane-intersection workflows.
    """

    def __init__(self, p1, p2):
        """Create a segment from two endpoints.

        Category: geometry primitive.
        Tags: segment, endpoints, point, direction-vector.
        Use when: constructing bounded geometry from two coordinates or points.
        Args:
            p1: First endpoint coordinate or ``Point``.
            p2: Second endpoint coordinate or ``Point``.
        Side effects:
            Initializes the parent line, stores endpoints as ``Point`` objects,
            and computes endpoint displacement.
        """
        super().__init__(p1, p2)
        self.p1 = Point(p1)
        self.p2 = Point(p2)
        self.displacement = self.p2 - self.p1

    def __repr__(self):
        return f"Segment(p1: {self.p1}, p2: {self.p2})"

    def __str__(self):
        return f"Segment(p1: {self.p1}, p2: {self.p2})"

    @property
    def length(self):
        """Return the Euclidean distance between segment endpoints.

        Category: geometry primitive.
        Tags: segment, length, distance.
        Use when: geometric workflows need the finite segment length.
        Returns:
            float: Norm of ``p2 - p1``.
        """
        return np.sqrt(np.sum(self.displacement ** 2))


    def intersect(self, primitive: BasePrimitive):
        """Intersect this segment with a supported primitive.

        Category: geometry primitive.
        Tags: segment, intersection, plane.
        Use when: clipping or testing a finite segment against a plane.
        Args:
            primitive: Currently only ``Plane`` is supported.
        Returns:
            Result returned by ``intersect_plane_segment``.
        Raises:
            NotImplementedError: If the primitive type is unsupported.
        """
        from .intersections import intersect_plane_segment

        if primitive.__class__.__name__ == "Plane":
            return intersect_plane_segment(segment=self, plane=primitive)

        else:
            raise NotImplementedError(f"Intersection of {type(self)} with {type(primitive)} is not implemented")

    def contains(self, point):
        # Calculate direction vectors
        """Return whether a point lies on the finite segment.

        Category: geometry primitive.
        Tags: segment, containment, point, bounds.
        Use when: verifying that a candidate intersection lies between segment
            endpoints.
        Args:
            point: Point-like coordinate to test.
        Returns:
            bool: ``True`` when the point is collinear with the segment and lies
            between both endpoints.
        """
        segment_vector = self.p2 - self.p1
        point_vector = point - self.p1

        # Check if point_vector is a scalar multiple of segment_vector
        cross_product = np.cross(segment_vector, point_vector)
        if not np.allclose(cross_product, 0):
            return False

        # Check if the point lies between the segment endpoints
        dot_product = np.dot(segment_vector, point_vector)
        segment_length_squared = np.dot(segment_vector, segment_vector)

        return 0 <= dot_product <= segment_length_squared

