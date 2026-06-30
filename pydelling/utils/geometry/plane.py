"""
Module documentation.


"""

from __future__ import annotations

from typing import List

import numpy as np

from .base_primitive import BasePrimitive
from .point import Point
from .vector import Vector


class Plane(BasePrimitive):
    """3D plane represented by a point and a normal vector.

    Category: geometry primitive.
    Tags: plane, point, normal, intersection, parallel.
    Use when: to use plane geometry for intersections with planes,
        lines, or segments.
    """

    def __init__(self, point: Point or List or np.ndarray, normal: List or Vector or np.ndarray):
        """Create a plane from an anchor point and normal vector.

        Category: geometry primitive.
        Tags: plane, point, normal, initialization.
        Use when: constructing a geometric plane for intersection or parallel
            checks.
        Args:
            point: Point-like anchor coordinate.
            normal: Vector-like plane normal.
        Side effects:
            Stores ``self.p`` as a ``Point`` and ``self.n`` as a ``Vector``.
        """
        self.p = Point(point)
        self.n = Vector(normal)

    def __repr__(self):
        return f"Plane(point:{self.p}, normal:{self.n})"

    def __str__(self):
        return f"Plane(point:{self.p}, normal:{self.n})"

    def intersect(self, primitive: BasePrimitive):
        """Return the intersection with a supported primitive.

        Category: geometry primitive.
        Tags: plane, intersection, line, segment.
        Use when: computing plane-plane, plane-line, or plane-segment
            intersections using pydelling helpers.
        Args:
            primitive: ``Plane``, ``Line``, or ``Segment`` instance.
        Returns:
            Result returned by the matching intersection helper.
        Raises:
            NotImplementedError: If the primitive type is unsupported.
        """
        from .intersections import intersect_plane_plane, intersect_plane_line, intersect_plane_segment
        if primitive.__class__.__name__ == "Plane":
            return intersect_plane_plane(plane_1=self, plane_2=primitive)
        elif primitive.__class__.__name__ == "Line":
            return intersect_plane_line(plane=self, line=primitive)
        elif primitive.__class__.__name__ == 'Segment':
            return intersect_plane_segment(plane=self, segment=primitive)

        else:
            raise NotImplementedError(f"Intersection with {type(primitive)} is not implemented")

    def is_parallel(self, plane: Plane):
        """Return whether another plane is parallel or anti-parallel.

        Category: geometry primitive.
        Tags: plane, parallel, normal.
        Use when: checking plane orientation before intersection operations.
        Args:
            plane: Other plane to compare against.
        Returns:
            bool | None: ``True`` when normals are parallel or anti-parallel;
            otherwise ``None``.
        """
        if np.isclose(np.dot(self.n, plane.n), 1):
            return True
        if np.isclose(np.dot(self.n, plane.n), -1):
            return True
