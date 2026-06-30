"""
Module documentation.


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class XDMFFilter(base_filter):
    """ParaView XDMF reader wrapper with cached coordinate ranges.

    Category: ParaView filter.
    Tags: paraview, xdmf, reader, bounds.
    Use when: an MCP agent needs to load an XDMF dataset into a ParaView
        pipeline and inspect its spatial extents.
    """

    filter_type: str = "XDMF_reader"
    counter: int = 0
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float

    def __init__(self, filename, name):
        """Create an XDMF reader filter.

        Category: ParaView filter.
        Tags: paraview, xdmf, initialization.
        Use when: reading XDMF files into a pydelling ParaView processor.
        Args:
            filename: XDMF file path.
            name: Logical filter name passed to the base filter wrapper.
        Side effects:
            Creates the ParaView ``XDMFReader`` proxy and computes coordinate
            ranges.
        """
        super().__init__(name=name)
        self.filter = XDMFReader(FileNames=str(filename))
        XDMFFilter.counter += 1
        self.set_ranges()

    def set_ranges(self):
        """Compute x/y/z ranges from mesh points.

        Category: ParaView filter.
        Tags: paraview, xdmf, bounds, coordinates.
        Use when: downstream filters or reports need XDMF spatial extents.
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
