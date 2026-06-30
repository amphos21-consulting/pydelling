"""
Module documentation.


"""

from __future__ import annotations

from typing import List

import numpy as np

from .base_primitive import BasePrimitive
from .point import Point


class Line(BasePrimitive):
    """Infinite 3D line represented by a point and a unit direction vector.

    Category: geometry primitive.
    Tags: line, point, direction-vector, intersection, angle.
    Use when: an MCP agent needs geometric line operations for intersections or
        angular comparisons.
    """

    def __init__(self, p1: np.ndarray or Point or List = None, p2: np.ndarray or Point or List = None,
                 direction_vector: np.ndarray or List = None):
        """Create a line from two points or from one point and a direction.

        Category: geometry primitive.
        Tags: line, point, direction-vector, initialization.
        Use when: constructing an infinite line for geometric intersection
            routines.
        Args:
            p1: First point, or the anchor point when ``direction_vector`` is
                provided.
            p2: Second point, or the anchor point when ``p1`` is omitted and
                ``direction_vector`` is provided.
            direction_vector: Direction vector normalized during construction.
        Side effects:
            Sets ``self.p`` to an anchor ``Point`` and ``self.direction_vector``
            to a normalized vector.
        """
        if p1 is not None and p2 is not None:
            p1 = Point(p1)
            p2 = Point(p2)
            self.direction_vector = (p2 - p1) / np.linalg.norm(p2 - p1)
            if isinstance(p1, Point):
                self.p = p1
            else:
                self.p = Point(p1)

        elif direction_vector is not None and (p1 is not None or p2 is not None):
            self.direction_vector = direction_vector / np.linalg.norm(direction_vector)

            if p1 is not None:
                if isinstance(p1, Point):
                    self.p = p1
                else:
                    self.p = Point(p1)
            elif p2 is not None:
                if isinstance(p2, Point):
                    self.p = p2
                else:
                    self.p = Point(p2)

    def is_parallel(self, line: Line):
        """Return whether another line is parallel or anti-parallel.

        Category: geometry primitive.
        Tags: line, parallel, direction-vector.
        Use when: checking geometric relationships before attempting line-line
            intersections.
        Args:
            line: Other ``Line`` instance to compare against.
        Returns:
            bool | None: ``True`` when direction vectors are parallel or
            anti-parallel; otherwise ``None``.
        """
        if np.isclose(np.dot(self.direction_vector, line.direction_vector), 1):
            return True
        if np.isclose(np.dot(self.direction_vector, line.direction_vector), -1):
            return True

    def angle(self, line: Line):
        """Compute the angle between this line and another line.

        Category: geometry primitive.
        Tags: line, angle, direction-vector.
        Use when: measuring angular relationships between two geometric lines.
        Args:
            line: Other ``Line`` instance.
        Returns:
            float: Angle in radians.
        """
        return np.arccos(np.dot(self.direction_vector, line.direction_vector) /
                         (np.linalg.norm(self.direction_vector) * np.linalg.norm(line.direction_vector)))

    def intersect(self, primitive: BasePrimitive):
        """Intersect this line with another supported primitive.

        Category: geometry primitive.
        Tags: line, intersection, plane.
        Use when: an MCP workflow needs the library's built-in line-line or
            line-plane intersection routines.
        Args:
            primitive: ``Line`` or ``Plane`` instance.
        Returns:
            Result returned by the matching intersection helper.
        Raises:
            NotImplementedError: If the primitive type is unsupported.
        """
        from .intersections import intersect_line_line, intersect_plane_line

        if primitive.__class__.__name__ == "Line":
            return intersect_line_line(line_1=self, line_2=primitive)
        elif primitive.__class__.__name__ == "Plane":
            return intersect_plane_line(line=self, plane=primitive)



        else:
            raise NotImplementedError(f"Intersection with {type(primitive)} is not implemented")


    def __repr__(self):
        return f"Line(point: {self.p}, direction_vector: {self.direction_vector})"

    def __str__(self):
        return f"Line(point: {self.p}, direction_vector: {self.direction_vector})"
