"""
This class takes a list of points and creates a collection of lines


"""

from typing import List

from .gid_object import GidObject
from .line import Line
from .point import Point


class Polyline(GidObject):
    """GID helper that converts ordered points into connected line objects.

    Category: GID preprocessing.
    Tags: gid, polyline, points, lines, geometry.
    Usage: to generate a chain or closed loop of GID line
        entities from point objects.
    """

    local_id: int = 1

    def __init__(self, points: List[Point], connect=False):
        """Create a polyline from ordered points.

        Category: GID preprocessing.
        Tags: gid, polyline, points, initialization.
        Usage: preparing a set of GID line objects from a point sequence.
        Args:
            points: Ordered points in the polyline.
            connect: If ``True``, add a closing line from the last point to the
                first.
        Side effects:
            Creates the line objects by calling ``set_up``.
        """
        super().__init__()
        self.lines = []
        self.points = points
        self.connect = connect
        self.set_up()

    def set_up(self):
        """Create line objects between consecutive polyline points.

        Category: GID preprocessing.
        Tags: gid, polyline, lines, setup.
        Usage: rebuilding the internal line list after point assignment.
        Side effects:
            Populates ``self.lines`` and optionally adds a closing line.
        """
        for idx, _ in enumerate(self.points[:-1]):
            point_a = self.points[idx]
            point_b = self.points[idx + 1]
            aux_line = Line(point_a, point_b)
            self.lines.append(aux_line)
        if self.connect:
            aux_line = Line(self.points[-1], self.points[0])
            self.lines.append(aux_line)

    def construct(self, *args, **kwargs):
        """Add all polyline points and lines to the GID object collection.

        Category: GID preprocessing.
        Tags: gid, polyline, construct, export.
        Usage: emitting or registering every object needed by the polyline.
        Args:
            *args: Accepted for ``GidObject`` API compatibility.
            **kwargs: Accepted for ``GidObject`` API compatibility.
        Side effects:
            Calls ``self.add`` for every point and generated line.
        """
        for point in self.points:
            self.add(point)
        for line in self.lines:
            self.add(line)
