"""
This class implements the Save Data filter


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class SaveDataFilter(base_filter):
    """ParaView SaveData wrapper for exporting selected arrays.

    Category: ParaView filter.
    Tags: paraview, save-data, export, cell-data, point-data.
    Use when: an MCP agent needs to persist a ParaView proxy with selected point
        and cell data arrays.
    """

    filter_type: str = "Save_data"
    counter: int = 0

    def __init__(self, filename, proxy, point_data_arrays, cell_data_arrays, name):
        """
        __init__ method.
        
        Args:
            filename (Any): Description.
            proxy (Any): Description.
            point_data_arrays (Any): Description.
            cell_data_arrays (Any): Description.
            name (Any): Description.
        """
        super().__init__(name=name)
        SaveDataFilter.counter += 1
        self.filter = SaveData(self, Input=filename, proxy=proxy)
        self.filter.Proxy = proxy
        self.filter.PointDataArrays = point_data_arrays
        self.filter.CellDataArrays = cell_data_arrays
