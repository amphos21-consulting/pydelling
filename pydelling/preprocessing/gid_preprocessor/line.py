"""
Module documentation.


"""

from __future__ import annotations

import logging
from typing import List

import numpy as np

from .point import Point
from ._abstract_fit_object import _AbstractGidObject

logger = logging.getLogger(__name__)

class Line(_AbstractGidObject):
    """GID line object connecting two distinct points.

    Category: GID preprocessing.
    Tags: gid, line, points, export, duplicate-detection.
    Use when: an MCP agent needs to create or reuse line definitions while
        generating GID geometry scripts.
    """

    local_id: int = 1
    global_id: int = 1
    lines: List = []
    has_copy = False
    def __init__(self, point_1: Point, point_2: Point):
        """Create a local GID line between two points.

        Category: GID preprocessing.
        Tags: gid, line, points, initialization.
        Use when: building GID geometry from point objects.
        Args:
            point_1: Start point object.
            point_2: End point object.
        Raises:
            ValueError: If both points have identical coordinates.
        Side effects:
            Assigns a local line id and increments the class local counter.
        """
        self.local_id = Line.local_id
        self.id = None
        if np.array_equal(point_1.coords, point_2.coords):
            raise ValueError('The start and end points of a line cannot be equal')
        self.point_1 = point_1
        self.point_2 = point_2
        self.points = [self.point_1, self.point_2]
        Line.local_id += 1

    def add(self):
        # Check if line already exists
        """Return the GID command that creates this line, unless it is a copy.

        Category: GID preprocessing.
        Tags: gid, line, export, duplicate-detection.
        Use when: emitting GID line commands while avoiding duplicate edge
            definitions.
        Returns:
            str: GID command text, or an empty string when an equivalent line
            already exists.
        Side effects:
            Sets the global id, updates duplicate state, and appends new lines
            to the class registry.
        """
        for line in Line.lines:
            if Line.check_lines_equal(self, line):
                self.id = line.id
                self.has_copy = True
                return ''

        self.id = Line.global_id
        Line.global_id += 1
        Line.lines.append(self)
        logger.info(f'Adding line {self.id} connecting {self.point_1} and {self.point_2}')
        export_str = 'Mescape Geometry Create Line\n'
        export_str += 'Join\n'
        export_str += f'{self.point_1.id}\n'
        export_str += f'{self.point_2.id}\n'
        return export_str

    @staticmethod
    def check_lines_equal(line_1: Line, line_2: Line):
        """Return whether two GID lines connect the same two points.

        Category: GID preprocessing.
        Tags: gid, line, duplicate-detection, connectivity.
        Use when: determining whether a line command should be skipped because
            the same edge already exists.
        Args:
            line_1: First line to compare.
            line_2: Second line to compare.
        Returns:
            bool: ``True`` when both endpoints match regardless of orientation.
        """
        point_1_coords = [line_1.point_1.coords.tolist(), line_1.point_2.coords.tolist()]
        if line_2.point_1.coords.tolist() in point_1_coords and line_2.point_2.coords.tolist() in point_1_coords:
            return True
        else:
            return False

    def __repr__(self):
        if self.id:
            return f"Line {self.id}"
        else:
            return f"Line (local) {self.local_id}"






