"""
Centroid file reader


"""
import logging

import numpy as np
import pandas as pd

from .base_reader import BaseReader

logger = logging.getLogger(__name__)


class CentroidReader(BaseReader):
    """Read centroid coordinate files with an optional associated variable.

    Category: centroid reader.
    Tags: centroids, coordinates, variable, csv, dataframe.
    Usage: to load x/y/z centroid locations and an
        optional scalar value from a text file.
    """

    def __init__(self, filename, var_pos=3, var_name="var", var_type=np.float32, centroid_pos=(0, 3), header=False, separator=None):
        """
        __init__ method.
        
        Args:
            filename (Any): Description.
            var_pos (Any): Description.
            var_name (Any): Description.
            var_type (Any): Description.
            centroid_pos (Any): Description.
            header (Any): Description.
            separator (Any): Description.
        """
        self.var_pos = var_pos
        self.var = None
        self.var_name = var_name
        self.var_type = var_type
        self.centroid_pos = centroid_pos
        self.header = header
        self.split_key = separator
        if self.var_pos:
            logger.info(f"Reading data using centroids in positions [{self.centroid_pos[0]}, {self.centroid_pos[1] - 1}] and data in position {self.var_pos}")
        else:
            logger.info(f"Reading data using centroids in positions [{self.centroid_pos[0]}, {self.centroid_pos[1] - 1}]")

        super().__init__(filename, var_pos=var_pos,
                         var_name=var_name,
                         var_type=var_type,
                         centroid_pos=centroid_pos,
                         header=header)

    def read_file(self, opened_file):
        """Parse centroid coordinates and optional variable values.

        Category: centroid reader.
        Tags: centroids, parse, text-file, variable.
        Usage: loading centroid rows from an already opened text file.
        Args:
            opened_file: Open file handle positioned at the centroid rows.
        Side effects:
            Sets ``self.data`` to centroid coordinates and ``self.var`` when a
            variable position is configured.
        """
        logger.info(f"Reading centroid file from {self.filename}")
        temp_centroid = []
        temp_id = []
        for line in opened_file.readlines():
            if self.split_key:
                data_row = line.split(self.split_key)
            else:
                data_row = line.split()
            temp_centroid.append(data_row[self.centroid_pos[0]:self.centroid_pos[1] + 1])
            if self.var_pos:
                temp_id.append([data_row[self.var_pos]])
        self.data = np.array(temp_centroid, dtype=np.float32)
        if self.var_pos:
            self.var = np.array(temp_id, dtype=self.var_type)


    def read_header(self):
        """Placeholder for centroid-file header parsing.

        Category: centroid reader.
        Tags: centroids, header, extension-point.
        Usage: implementing support for centroid formats with explicit
            headers.
        Notes:
            The current implementation does not parse header content.
        """
        pass

    def get_data(self, as_dataframe=False) -> pd.DataFrame:
        """Return centroid data as a NumPy array or DataFrame.

        Category: centroid reader.
        Tags: centroids, data, dataframe, numpy.
        Usage: downstream processing needs parsed centroid coordinates and,
            when configured, the associated variable values.
        Args:
            as_dataframe: If ``True``, return a pandas DataFrame with named
                columns.
        Returns:
            np.ndarray | pd.DataFrame: Parsed centroid coordinates, optionally
            converted to a DataFrame.
        """
        if as_dataframe:
            if self.var_pos:
                return pd.DataFrame(self.data, columns=['x', 'y', 'z', f"{self.var_name}"])
            else:
                return pd.DataFrame(self.data, columns=['x', 'y', 'z'])
        else:
            return self.data


    def build_info(self):
        """Build metadata for the parsed centroid file.

        Category: centroid reader.
        Tags: centroids, metadata, info.
        Usage: MCP tools need cell count, source filename, and variable
            metadata after parsing.
        Side effects:
            Updates ``self.info["reader"]``.
        """
        self.info["reader"] = {"n_cells": self.data.shape[0],
                     "filename": self.filename,
                     "var_name": self.var_name,
                     "var_position": self.var_pos}

    def to_csv(self, output_file, delimiter=","):
        """Write parsed centroid data to a delimited text file.

        Category: centroid reader.
        Tags: centroids, csv, export.
        Usage: exporting loaded centroid coordinates for another tool.
        Args:
            output_file: Destination file path.
            delimiter: Output delimiter.
        Side effects:
            Writes ``self.get_data()`` to ``output_file``.
        """
        logger.info(f"Starting dump into {output_file}")
        np.savetxt(output_file, self.get_data(), delimiter=delimiter)
        logger.info(f"The data has been properly exported to the {output_file} file")

    def shift(self, direction=np.array([0.0, 0.0, 0.0])):
        """Shift centroid coordinates by a direction vector.

        Category: centroid reader.
        Tags: centroids, coordinates, transform, shift.
        Usage: converting centroid coordinates between local and translated
            coordinate systems.
        Args:
            direction: 3D offset added to the first three data columns.
        Side effects:
            Mutates ``self.data`` in place.
        """
        if type(direction) is list:
            direction = np.array(direction)
        self.data[:, 0:3] += direction
