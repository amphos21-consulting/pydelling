"""
Module documentation.


"""

from ._abstract_fit_object import _AbstractGidObject
from .line import Line
from .point import Point
import logging
from typing import List
import logging
from typing import List

from ._abstract_fit_object import _AbstractGidObject

logger = logging.getLogger(__name__)


class Surface(_AbstractGidObject):
    """GID NURBS surface built from boundary lines.

    Category: GID preprocessing.
    Tags: gid, surface, nurbs, lines, extrusion.
    Use when: an MCP agent needs to create GID surface commands from previously
        defined line objects.
    """

    local_id: int = 1
    global_id: int = 1
    surfaces: List = []

    def __init__(self, lines: List[Line]):
        """Create a local surface from boundary lines.

        Category: GID preprocessing.
        Tags: gid, surface, lines, initialization.
        Use when: grouping GID line objects into a surface definition.
        Args:
            lines: Boundary ``Line`` objects that define the surface.
        Side effects:
            Assigns a local surface id and increments the class local counter.
        """
        self.local_id = Surface.local_id
        self.lines = lines
        self.id = None
        Surface.local_id += 1

    def add(self):
        """Return the GID command that creates this surface.

        Category: GID preprocessing.
        Tags: gid, surface, export, nurbs.
        Use when: emitting GID commands for surface creation.
        Returns:
            str: GID command text for creating the NURBS surface.
        Side effects:
            Assigns a global surface id and appends the surface to the class
            registry.
        """
        self.id = Surface.global_id
        logger.info(f'Adding surface {self.id} connecting {self.lines}')
        Surface.global_id += 1
        Surface.surfaces.append(self)
        export_str = 'Mescape Geometry Create NurbsSurface\n'
        for line in self.lines:
            export_str += f'{line.id} '
        export_str += '\n'
        return export_str

    def extrude(self, start_point: Point, end_point: Point, end_object):
        """Return the GID command that extrudes this surface.

        Category: GID preprocessing.
        Tags: gid, surface, extrusion, translation.
        Use when: generating GID commands to extrude a surface between two
            points.
        Args:
            start_point: Start point for the extrusion vector.
            end_point: End point for the extrusion vector.
            end_object: GID extrusion target selector used in the command.
        Returns:
            str: GID extrusion command text.
        Side effects:
            Advances global counters for generated surfaces, lines, and points.
        """
        logger.info(f'Extruding {self} using direction {start_point.coords} -> {end_point.coords}')
        export_str = f'Mescape Utilities Copy Surfaces DoExtrude {end_object} MaintainLayers Translation FNoJoin {start_point.coords_comma} FNoJoin {end_point.coords_comma}\n'
        export_str += f'{self.id}\n'
        extra_surfaces = 5
        extra_lines = 2 * len(self.lines)
        extra_points = len(self.lines)
        Surface.global_id += extra_surfaces
        Line.global_id += extra_lines
        Point.global_id += extra_points
        return export_str

    def __repr__(self):
        if self.id:
            return f"Surface {self.id}"
        else:
            return f"Surface (local) {self.local_id}"
