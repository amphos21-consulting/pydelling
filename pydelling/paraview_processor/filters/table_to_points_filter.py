"""
This class implements the Table to Points filter


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class TableToPointsFilter(base_filter):
    filter_type: str = "Table_to_points"
    counter: int = 0

    def __init__(self, filename, name, **params):
        """
        __init__ method.
        
        Args:
            filename (Any): Description.
            name (Any): Description.
            **params (Any): Description.
        """
        super().__init__(name=name)
        TableToPointsFilter.counter += 1
        self.filter = TableToPoints(Input=str(filename))
        for param in params:
            setattr(self.filter, param, params[param])

    def table2points_columns(self, x_column, y_column, z_column):
        """
        This method sets de xyz columns
        
        Args:
            x_column (Any): Description.
            y_column (Any): Description.
            z_column (Any): Description.
        """
        self.filter.Xcolumn = x_column
        self.filter.Ycolumn = y_column
        self.filter.Zcolumn = z_column
