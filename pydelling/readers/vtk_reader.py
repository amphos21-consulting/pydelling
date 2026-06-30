"""
This class provides the framework to read data from a VTK file and do different postprocessing steps


"""

from .base_reader import BaseReader
try:
    from paraview.simple import *
    from paraview.vtk.numpy_interface import dataset_adapter as dsa
    from paraview import servermanager as sm
except:
    pass


class VtkReader(BaseReader):
    """Read legacy VTK files through ParaView and expose point data.

    Category: reader
    Tags: vtk, paraview, point-data, calculator, postprocessing
    Usage: scripts need ParaView-backed access to VTK point arrays or calculator filters.
    """
    current_array: None
    calculator: None

    def read_file(self, opened_file):
        """Load the configured VTK file with ParaView's LegacyVTKReader.

        Category: reader
        Tags: vtk, paraview, reader, legacy
        Usage: scripts need a VTK file registered as the current ParaView pipeline source.

        Returns:
            None: stores vtk_file and current_array.
        """
        self.vtk_file = LegacyVTKReader(FileNames=self.filename)
        self.current_array = self.vtk_file

    @property
    def values(self):
        """Return point-data values from the current ParaView array.

        Category: reader
        Tags: vtk, paraview, point-data, values
        Usage: scripts need point-data arrays after optional filter processing.

        Returns:
            Any: wrapped VTK PointData object.
        """
        _vtk_object = sm.Fetch(self.current_array)
        _vtk_object = dsa.WrapDataObject(_vtk_object)
        return _vtk_object.PointData

    @property
    def keys(self):
        """Return the current ParaView array/filter object.

        Category: reader
        Tags: vtk, paraview, current-array, metadata
        Usage: scripts need access to the active pipeline object.

        Returns:
            object: current ParaView array or filter proxy.
        """
        return self.current_array

    @property
    def data_keys(self):
        """Return point-data array keys from the original VTK source.

        Category: reader
        Tags: vtk, paraview, point-data, keys
        Usage: scripts need to inspect available arrays in the loaded VTK file.

        Returns:
            list: point-data keys from the VTK source.
        """
        _vtk_object = sm.Fetch(self.vtk_file)
        return self.vtk_file.PointData.keys()

    @property
    def data_values(self):
        """Return point-data values from the original VTK source.

        Category: reader
        Tags: vtk, paraview, point-data, values
        Usage: scripts need raw VTK point data before calculator filters.

        Returns:
            Any: wrapped VTK PointData object.
        """
        _vtk_object = sm.Fetch(self.vtk_file)
        _vtk_object = dsa.WrapDataObject(_vtk_object)
        return _vtk_object.PointData

    def add_calculator(self, input=None, function=''):
        """Add a ParaView Calculator filter to the current pipeline.

        Category: postprocessing
        Tags: vtk, paraview, calculator, filter
        Usage: scripts need a derived array expression evaluated on a VTK dataset.

        Returns:
            object: calculator filter proxy now set as current_array.
        """
        input = input if input else self.current_array
        self.calculator = Calculator(Input=input)
        self.calculator.Function = function

        self.current_array = self.calculator
        return self.current_array
