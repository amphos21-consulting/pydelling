"""
This class implements the Table to Points filter


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class TableToPointsFilter(base_filter):
    """ParaView TableToPoints wrapper for tabular coordinate data.

    Category: ParaView filter.
    Tags: paraview, table-to-points, coordinates, csv.
    Use when: an MCP agent needs to configure a ParaView table source as point
        geometry.
    """

    filter_type: str = "Table_to_points"
    counter: int = 0

    def __init__(self, filename, name, **params):
        """Create a TableToPoints proxy and apply parameters.

        Category: ParaView filter.
        Tags: paraview, table-to-points, initialization.
        Use when: converting a table-like source into a point source.
        Args:
            filename: Input table source or filename passed to ParaView.
            name: Logical filter name passed to the base filter wrapper.
            **params: ParaView filter attributes to set after construction.
        Side effects:
            Creates the ParaView ``TableToPoints`` proxy and sets provided
            attributes.
        """
        super().__init__(name=name)
        TableToPointsFilter.counter += 1
        self.filter = TableToPoints(Input=str(filename))
        for param in params:
            setattr(self.filter, param, params[param])

    def table2points_columns(self, x_column, y_column, z_column):
        """Set the table columns used as x/y/z coordinates.

        Category: ParaView filter.
        Tags: paraview, table-to-points, coordinates.
        Use when: selecting coordinate columns for point conversion.
        Args:
            x_column: Column name for x coordinates.
            y_column: Column name for y coordinates.
            z_column: Column name for z coordinates.
        Side effects:
            Updates the ParaView TableToPoints coordinate column properties.
        """
        self.filter.Xcolumn = x_column
        self.filter.Ycolumn = y_column
        self.filter.Zcolumn = z_column
