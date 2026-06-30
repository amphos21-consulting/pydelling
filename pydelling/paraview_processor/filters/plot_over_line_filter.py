"""
This class implements the PlotOverLine paraview filter


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
    from paraview.vtk.numpy_interface import dataset_adapter as dsa
    from paraview.vtk.numpy_interface import algorithms as algs
    from paraview import servermanager as sm
except:
    pass


import pandas as pd
import numpy as np


class PlotOverLineFilter(base_filter):
    """ParaView PlotOverLine wrapper that samples data along a segment.

    Category: ParaView filter.
    Tags: paraview, plot-over-line, sampling, point-data.
    Use when: an MCP agent needs to configure line sampling in a ParaView
        processing pipeline and retrieve sampled point data.
    """

    filter_type: str = "PlotOverLineFilter"
    counter: int = 0

    def __init__(self, input_filter, name, point_1=None, point_2=None, n_line=None):
        """Create a PlotOverLine filter and optionally configure its line.

        Category: ParaView filter.
        Tags: paraview, plot-over-line, initialization, sampling.
        Use when: adding a line-sampling filter to an existing ParaView source.
        Args:
            input_filter: Upstream ParaView proxy to sample.
            name: Logical filter name passed to the base filter wrapper.
            point_1: Optional first endpoint of the sampling line.
            point_2: Optional second endpoint of the sampling line.
            n_line: Optional sampling resolution.
        Raises:
            AssertionError: If only one endpoint is provided.
        Side effects:
            Creates a ParaView ``PlotOverLine`` proxy and applies optional line
            endpoints and resolution.
        """
        super().__init__(name=name)
        PlotOverLineFilter.counter += 1
        self.filter = PlotOverLine(Input=input_filter)
        if point_1:
            assert point_2, "Two points need to be defined"
        if point_2:
            assert point_1, "Two points need to be defined"
        if point_1 or point_2:
            self.filter.Point1 = point_1
            self.filter.Point2 = point_2
        if n_line:
            self.filter.Resolution = n_line

    def set_points(self, point_1, point_2):
        """Set the sampling line endpoints.

        Category: ParaView filter.
        Tags: paraview, plot-over-line, endpoints.
        Use when: changing the line segment sampled by the filter.
        Args:
            point_1: First point of the line
            point_2: Second point of the line
        Side effects:
            Mutates ``self.filter.Point1`` and ``self.filter.Point2``.
        """
        self.filter.Point1 = point_1
        self.filter.Point2 = point_2

    def set_line_resolution(self, n):
        """Set the number of line samples.

        Category: ParaView filter.
        Tags: paraview, plot-over-line, resolution.
        Use when: changing how many divisions are sampled along the line.
        Args:
            n: Number specifying the number of divisions of the line used to interpolate the data on.
        Side effects:
            Mutates ``self.filter.Resolution``.
        """
        self.filter.Resolution = n

    @property
    def point_data(self):
        """Return sampled point data as a DataFrame.

        Category: ParaView filter.
        Tags: paraview, plot-over-line, point-data, dataframe.
        Use when: extracting line-sampled scalar or vector arrays for analysis.
        Returns:
            pd.DataFrame: Sampled point arrays, with vector components expanded
            using ``vector_keys``.
        """
        vtk_object = sm.Fetch(self.filter)
        vtk_object = dsa.WrapDataObject(vtk_object)
        pd_df = pd.DataFrame()
        for key in self.point_keys:
            temp_dataset = np.array(vtk_object.PointData[key]).transpose()
            if len(temp_dataset.shape) != 1:
                # The dataset is a vector:
                for idx, vector_element in enumerate(temp_dataset):
                    new_key = f"{key}{self.vector_keys[idx]}"
                    pd_df[new_key] = vector_element
            else:
                pd_df[key] = temp_dataset
        return pd_df.dropna()
