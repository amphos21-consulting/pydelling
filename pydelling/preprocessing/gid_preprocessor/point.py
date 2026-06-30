"""
Module documentation.


"""

import logging
from typing import List

import numpy as np

from ._abstract_fit_object import _AbstractGidObject

logger = logging.getLogger(__name__)

class Point(_AbstractGidObject):
    """GID point object with duplicate detection and export command generation.

    Category: GID preprocessing.
    Tags: gid, point, geometry, export, coordinates.
    Usage: to create or reuse point definitions while
        generating GID geometry scripts.
    """

    has_copy = False
    local_id: int = 1
    global_id: int = 1
    points: List = []
    def __init__(self, coords):
        """Create a local point from a 3D coordinate.

        Category: GID preprocessing.
        Tags: gid, point, coordinates, initialization.
        Usage: building GID geometry from coordinate lists or NumPy arrays.
        Args:
            coords: Three-dimensional coordinate as a list or NumPy array.
        Raises:
            AssertionError: If the coordinate is not a 3D list or NumPy array.
        Side effects:
            Assigns a local point id and increments the class local counter.
        """
        self.local_id = Point.local_id
        self.id = None
        Point.local_id += 1
        if isinstance(coords, list):
            coords = np.array(coords)
            assert coords.shape[0] == 3, 'A 3D coordinate needs to be given'
        assert isinstance(coords, np.ndarray), 'Please provide a numpy array or a list'
        self.coords = coords

    def add(self):
        """Return the GID command that creates this point, unless it is a copy.

        Category: GID preprocessing.
        Tags: gid, point, export, duplicate-detection.
        Usage: emitting GID geometry commands while avoiding duplicate point
            definitions.
        Returns:
            str: GID command text, or an empty string when an identical point was
            already registered.
        Side effects:
            Sets the global id, updates duplicate state, and appends new points
            to the class registry.
        """
        for point in Point.points:
            if np.array_equal(point.coords, self.coords):
                self.id = point.id
                self.has_copy = True
                return ''

        self.id = Point.global_id
        Point.global_id += 1
        Point.points.append(self)
        logger.info(f'Adding point {self.id} at {self.coords}')
        export_str = 'Mescape Geometry Create Point\n'
        export_str += f'{",".join(map(str, self.coords))}\n'
        return export_str

    @property
    def coords_comma(self):
        """Return coordinates formatted for GID command text.

        Category: GID preprocessing.
        Tags: gid, point, coordinates, formatting.
        Usage: constructing GID commands that expect comma-separated
            coordinate values.
        Returns:
            str: Comma-separated coordinate string.
        """
        return f'{",".join(map(str, self.coords))}'

    def __repr__(self):
        if self.id:
            return f"Point {self.id} ({self.coords})"
        else:
            return f"Point (local) {self.local_id} ({self.coords})"


