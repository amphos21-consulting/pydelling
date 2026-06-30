"""
Module documentation.


"""

from typing import List

import numpy as np

from pydelling.utils.geometry_utils import order_points_clockwise
from . import Point, Segment
from .base_primitive import BasePrimitive


class Polygon(BasePrimitive):
    """Planar polygon represented by ordered points and boundary segments.

    Category: geometry primitive.
    Tags: polygon, points, segments, csv.
    Use when: to use polygon boundary geometry for export or
        intersection workflows.
    """

    def __init__(self, points: List[Point] or np.ndarray):
        # The set of points should be ordered in a clockwise fashion
        """Create a polygon from points ordered clockwise.

        Category: geometry primitive.
        Tags: polygon, points, ordering, segments.
        Use when: constructing a closed polygon boundary from point coordinates.
        Args:
            points: Point objects or coordinate array defining polygon vertices.
        Side effects:
            Orders points clockwise and creates segment edges.
        """
        self.points = order_points_clockwise(points)
        self.segments = self.generate_segments()

    def generate_segments(self):
        """Create segment edges between consecutive polygon points.

        Category: geometry primitive.
        Tags: polygon, segments, edges.
        Use when: downstream geometry routines need explicit polygon boundary
            segments.
        Returns:
            list: ``Segment`` objects connecting each point to the next and
            closing the polygon.
        """
        segments = []
        for i in range(len(self.points)):
            segments.append(Segment(self.points[i], self.points[(i + 1) % len(self.points)]))
        return segments

    def to_csv(self, filename='polygon.csv'):
        """Write polygon vertices to a CSV file.

        Category: geometry primitive.
        Tags: polygon, csv, export, points.
        Use when: exporting polygon coordinates for inspection or external
            processing.
        Args:
            filename: Destination CSV filename.
        Side effects:
            Writes one row per polygon point.
        """
        import csv
        with open(filename, 'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=',')
            for point in self.points:
                writer.writerow(point)

                


