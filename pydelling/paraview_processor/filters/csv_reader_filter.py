"""
Module documentation.


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass
from functools import wraps


def convert_to_table(func):
    @wraps(func)
    def wrapper():

        func()
    return wrapper


class CsvReaderFilter(base_filter):
    """ParaView CSV reader wrapper that converts tabular coordinates to points.

    Category: ParaView filter.
    Tags: paraview, csv, table-to-points, coordinates, bounds.
    Use when: to load CSV point data into a ParaView pipeline
        and expose x/y/z ranges.
    """

    filter_type: str = "VTK_reader"
    counter: int = 0
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float

    def __init__(self, filename, name, coordinate_labels=("x", "y", "z")):
        """Create a CSV reader and convert it to a point-data source.

        Category: ParaView filter.
        Tags: paraview, csv, table-to-points, initialization.
        Use when: constructing a ParaView point source from a CSV file.
        Args:
            filename: CSV file path passed to ParaView ``CSVReader``.
            name: Logical filter name passed to the base filter wrapper.
            coordinate_labels: Column names used as x, y, and z coordinates.
        Side effects:
            Creates a CSV reader, converts it through ``TableToPoints``, and
            stores coordinate ranges.
        """
        super().__init__(name=name)
        self.filter = CSVReader(FileName=str(filename))
        CsvReaderFilter.counter += 1
        self.coordinate_labels = coordinate_labels
        self.filter = self.convert_table_to_points()
        self.set_ranges()

    def set_ranges(self):
        """Compute x/y/z ranges from the converted point mesh.

        Category: ParaView filter.
        Tags: paraview, csv, bounds, coordinates.
        Use when: a workflow needs quick spatial extents for CSV point data.
        Side effects:
            Sets ``x_min``, ``x_max``, ``y_min``, ``y_max``, ``z_min``, and
            ``z_max`` from ``mesh_points``.
        """
        self.x_min = self.mesh_points.min()["x"]
        self.x_max = self.mesh_points.max()["x"]
        self.y_min = self.mesh_points.min()["y"]
        self.y_max = self.mesh_points.max()["y"]
        self.z_min = self.mesh_points.min()["z"]
        self.z_max = self.mesh_points.max()["z"]

    def convert_table_to_points(self):
        """Convert the CSV table proxy into a ParaView point source.

        Category: ParaView filter.
        Tags: paraview, csv, table-to-points, coordinates.
        Use when: ParaView filters need CSV rows represented as geometric
            points.
        Returns:
            ParaView proxy returned by ``TableToPoints``.
        """
        _table_to_points = TableToPoints(Input=self.filter)
        _table_to_points.XColumn = self.coordinate_labels[0]
        _table_to_points.YColumn = self.coordinate_labels[1]
        _table_to_points.ZColumn = self.coordinate_labels[2]
        return _table_to_points
