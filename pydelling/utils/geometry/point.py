"""
Module documentation.


"""

from __future__ import annotations

import numpy as np


class Point(np.ndarray):
    """Numpy-backed 2D or 3D point geometry primitive.

    Category: util
    Tags: geometry, point, numpy, distance, serialization
    Use when: scripts need a lightweight point object compatible with numpy operations.
    """
    def __new__(cls, input_array):
        # Input array is an already formed ndarray instance
        # We first cast to be our class type
        """Create a Point from a 2D or 3D coordinate array.

        Category: util
        Tags: geometry, point, numpy, coordinates
        Use when: converting coordinate arrays into Point instances for geometry routines.

        Returns:
            Point: numpy ndarray view with point helpers.
        """
        if len(input_array) == 1:
            raise ValueError("Point must have 2 or 3 coordinates")
        elif len(input_array) == 2:
            obj = np.asarray(input_array).view(cls)
        elif len(input_array) == 3:
            obj = np.asarray(input_array).view(cls)
        else:
            raise ValueError("Point must have 2 or 3 coordinates")
        return obj

    def distance(self, p: Point):
        """Compute Euclidean distance to another point.

        Category: util
        Tags: geometry, point, distance
        Use when: geometry routines need scalar distance between two points.

        Returns:
            float: Euclidean distance.
        """
        diff = self - p
        return float(np.sqrt((diff ** 2).sum()))

    def __repr__(self):
        return f"Point({self})"


    @property
    def x(self):
        """Return the x coordinate.

        Category: util
        Tags: geometry, point, coordinate, x
        Use when: callers need named access to coordinate 0.

        Returns:
            float: x coordinate value.
        """
        return self[0]

    @property
    def y(self):
        """Return the y coordinate.

        Category: util
        Tags: geometry, point, coordinate, y
        Use when: callers need named access to coordinate 1.

        Returns:
            float: y coordinate value.
        """
        return self[1]

    @property
    def z(self):
        """Return the z coordinate.

        Category: util
        Tags: geometry, point, coordinate, z
        Use when: callers need named access to coordinate 2.

        Returns:
            float: z coordinate value.
        """
        return self[2]

    def get_json(self):
        """Return this point as a JSON-serializable coordinate list.

        Category: writer
        Tags: geometry, point, json, serialize
        Use when: scripts need to persist point coordinates.

        Returns:
            list: x, y, z coordinate values.
        """
        return [self.x, self.y, self.z]
