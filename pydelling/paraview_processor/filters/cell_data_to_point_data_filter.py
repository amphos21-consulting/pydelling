"""
This class implements the Paraview Integrate Variables filter


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class CellDataToPointDataFilter(base_filter):
    """ParaView CellDataToPointData filter wrapper.

    Category: ParaView filter.
    Tags: paraview, cell-data, point-data, conversion.
    Usage: to convert cell-centered arrays into point data
        for visualization or sampling.
    """

    filter_type: str = "Cell_data_to_point_data"
    counter: int = 0

    def __init__(self, input_filter, name):
        """
        __init__ method.
        
        Args:
            input_filter (Any): Description.
            name (Any): Description.
        """
        super().__init__(name=name)
        CellDataToPointDataFilter.counter += 1
        self.filter = CellDatatoPointData(Input=input_filter)
