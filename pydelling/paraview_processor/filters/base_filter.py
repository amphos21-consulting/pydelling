"""
Class used as a basecase class for the different Paraview filters


"""

import numpy as np
import pandas as pd

try:
    from paraview.vtk.numpy_interface import dataset_adapter as dsa
    from paraview.vtk.numpy_interface import algorithms as algs
    from paraview import servermanager as sm
    from paraview.simple import *
except:
    pass
from vtk.util.numpy_support import vtk_to_numpy
from typing import List
import logging

logger = logging.getLogger(__name__)


class BaseFilter:
    """Base wrapper for ParaView filters and data extraction helpers.

    Category: postprocessing
    Tags: paraview, filter, dataframe, vtk, export
    Use when: implementing ParaView filter wrappers with common data access and CSV export behavior.
    """
    filter_type: str = "VTK_reader"
    counter: int = 0
    filter: object
    vector_keys: List = ["x", "y", "z"]
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float

    def __init__(self, name):
        """Initialize a filter wrapper with a pipeline name.

        Category: postprocessing
        Tags: paraview, filter, pipeline, name
        Use when: concrete filter wrappers need shared naming behavior.

        Returns:
            None: stores the filter name.
        """
        self.name = name


    @property
    def cell_keys(self):
        """Return available cell-data array names.

        Category: postprocessing
        Tags: paraview, cell-data, arrays, keys
        Use when: scripts need to inspect cell-centered arrays in a ParaView filter.

        Returns:
            list: cell-data keys from the fetched VTK object.
        """
        vtk_object = sm.Fetch(self.filter)
        vtk_object = dsa.WrapDataObject(vtk_object)
        return vtk_object.CellData.keys()

    @property
    def point_keys(self):
        """Return available point-data array names.

        Category: postprocessing
        Tags: paraview, point-data, arrays, keys
        Use when: scripts need to inspect point-centered arrays in a ParaView filter.

        Returns:
            list: point-data keys from the fetched VTK object.
        """
        vtk_object = sm.Fetch(self.filter)
        vtk_object = dsa.WrapDataObject(vtk_object)
        return vtk_object.PointData.keys()

    @property
    def field_keys(self):
        """Return available field-data array names.

        Category: postprocessing
        Tags: paraview, field-data, arrays, keys
        Use when: scripts need to inspect field metadata arrays in a ParaView filter.

        Returns:
            list: field-data keys from the fetched VTK object.
        """
        vtk_object = sm.Fetch(self.filter)
        vtk_object = dsa.WrapDataObject(vtk_object)
        return vtk_object.FieldData.keys()

    @property
    def cell_data(self) -> pd.DataFrame:
        """Return cell-data arrays as a pandas DataFrame.

        Category: postprocessing
        Tags: paraview, cell-data, dataframe, arrays
        Use when: scripts need tabular access to cell-centered ParaView data.

        Returns:
            pandas.DataFrame: scalar arrays and expanded vector components.
        """
        vtk_object = sm.Fetch(self.filter)
        vtk_object = dsa.WrapDataObject(vtk_object)
        pd_df = pd.DataFrame()
        for key in self.cell_keys:
            temp_dataset = np.array(vtk_object.CellData[key]).transpose()
            if len(temp_dataset.shape) != 1:
                # The dataset is a vector:
                for idx, vector_element in enumerate(temp_dataset):
                    new_key = f"{key}{self.vector_keys[idx]}"
                    pd_df[new_key] = vector_element
            else:
                pd_df[key] = temp_dataset
        return pd_df

    @property
    def point_data(self) -> pd.DataFrame:
        """Return point-data arrays as a pandas DataFrame.

        Category: postprocessing
        Tags: paraview, point-data, dataframe, arrays
        Use when: scripts need tabular access to point-centered ParaView data.

        Returns:
            pandas.DataFrame: scalar arrays and expanded vector components.
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
        return pd_df


    @property
    def field_data(self) -> pd.DataFrame:
        """Return field-data arrays as a pandas DataFrame.

        Category: postprocessing
        Tags: paraview, field-data, dataframe, arrays
        Use when: scripts need tabular access to ParaView field metadata.

        Returns:
            pandas.DataFrame: scalar arrays and expanded vector components.
        """
        vtk_object = sm.Fetch(self.filter)
        vtk_object = dsa.WrapDataObject(vtk_object)
        pd_df = pd.DataFrame()
        for key in self.field_keys:
            temp_dataset = np.array(vtk_object.FieldData[key]).transpose()
            if len(temp_dataset.shape) != 1:
                # The dataset is a vector:
                for idx, vector_element in enumerate(temp_dataset):
                    new_key = f"{key}{self.vector_keys[idx]}"
                    pd_df[new_key] = vector_element
            else:
                pd_df[key] = temp_dataset
        return pd_df

    @property
    def mesh_points(self) -> pd.DataFrame:
        """Return mesh point coordinates as a DataFrame.

        Category: postprocessing
        Tags: paraview, mesh-points, coordinates, dataframe
        Use when: scripts need x,y,z coordinates from a ParaView filter output.

        Returns:
            pandas.DataFrame: point coordinates with x, y, z columns.
        """
        vtk_object = sm.Fetch(self.filter)
        return pd.DataFrame(vtk_to_numpy(vtk_object.GetPoints().GetData()), columns=["x", "y", "z"])

    def add_attribute(self, name: str, value: object):
        """Set an attribute on the underlying ParaView filter.

        Category: postprocessing
        Tags: paraview, filter, attribute, configuration
        Use when: scripts need to configure a ParaView proxy property dynamically.

        Returns:
            None: sets the proxy attribute.
        """

        setattr(self.filter, name, value)
        logger.info(f"Attribute {name} = {value} has been added to {self.name}")

    def to_csv(self, filename=None):
        """Export this filter's current data through ParaView SaveData.

        Category: writer
        Tags: paraview, csv, export, save-data
        Use when: scripts need a CSV artifact from the current ParaView filter output.

        Returns:
            None: writes the CSV file.
        """
        filename = filename if filename else f"{self.name}_filter_data.csv"
        SaveData(filename=filename, proxy=self.filter)
        logger.info(f"Saving {self.name} data into {filename}")
