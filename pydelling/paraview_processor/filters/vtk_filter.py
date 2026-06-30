"""
Module documentation.


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class VtkFilter(base_filter):
    """ParaView legacy VTK reader wrapper with cached coordinate ranges.

    Category: ParaView filter.
    Tags: paraview, vtk, reader, bounds.
    Use when: to load a legacy VTK dataset into a ParaView
        pipeline and inspect its spatial extents.
    """

    filter_type: str = "VTK_reader"
    counter: int = 0
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float

    def __init__(self, filename, name):
        """Create a legacy VTK reader filter.

        Category: ParaView filter.
        Tags: paraview, vtk, initialization.
        Use when: reading VTK files into a pydelling ParaView processor.
        Args:
            filename: VTK file path.
            name: Logical filter name passed to the base filter wrapper.
        Side effects:
            Creates the ParaView ``LegacyVTKReader`` proxy and computes
            coordinate ranges.
        """
        super().__init__(name=name)
        self.filter = LegacyVTKReader(FileNames=str(filename))
        VtkFilter.counter += 1
        self.set_ranges()

    def set_ranges(self):
        """Compute x/y/z ranges from mesh points.

        Category: ParaView filter.
        Tags: paraview, vtk, bounds, coordinates.
        Use when: downstream filters or reports need VTK spatial extents.
        Side effects:
            Sets ``x_min``, ``x_max``, ``y_min``, ``y_max``, ``z_min``, and
            ``z_max``.
        """
        self.x_min = self.mesh_points.min()["x"]
        self.x_max = self.mesh_points.max()["x"]
        self.y_min = self.mesh_points.min()["y"]
        self.y_max = self.mesh_points.max()["y"]
        self.z_min = self.mesh_points.min()["z"]
        self.z_max = self.mesh_points.max()["z"]
