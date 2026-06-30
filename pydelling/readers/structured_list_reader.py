"""
Centroid file reader


"""
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from pydelling.config import config
from .base_reader import BaseReader

logger = logging.getLogger(__name__)


class StructuredListReader(BaseReader):
    """Read structured list values into x,y,z,value rows.

    Category: reader
    Tags: structured-list, grid, coordinates, values, csv
    Usage: scripts need a config-defined structured grid list converted to tabular point data.
    """
    data: pd.DataFrame
    def __init__(self, filename=None, var_pos=3, var_name="var", var_type=np.float32, centroid_pos=(0, 3), header=False):
        """
        __init__ method.
        
        Args:
            filename (Any): Description.
            var_pos (Any): Description.
            var_name (Any): Description.
            var_type (Any): Description.
            centroid_pos (Any): Description.
            header (Any): Description.
        """
        self.var_pos = None
        self.var = None
        self.var_name = None
        self.var_type = None
        self.centroid_pos = None
        self.header = None
        self.filename = Path(filename) if filename else Path(config.structured_list_reader.filename)
        self.data: pd.DataFrame
        super().__init__(self.filename, var_pos=var_pos,
                         var_name=var_name,
                         var_type=var_type,
                         centroid_pos=centroid_pos,
                         header=header)

    def open_file(self, filename):
        """Open and read the configured structured list file.

        Category: reader
        Tags: structured-list, open, grid, values
        Usage: BaseReader calls open_file and the reader should populate data from config.

        Returns:
            None: delegates to read_file.
        """
        self.read_file()

    def read_file(self):
        """Read structured grid values from the configured list file.

        Category: reader
        Tags: structured-list, grid, coordinates, values
        Usage: scripts need x,y,z coordinates generated from configured origin, spacing, and dimensions.

        Returns:
            None: populates data with x, y, z, and v columns.
        """
        logger.info(f"Reading list file from {self.filename.stem}")
        _temp_array = []
        with open(config.structured_list_reader.filename, "r") as reading_file:
            for _ in range(config.structured_list_reader.header_offset):
                _read = reading_file.readline()
            for nz in range(config.structured_list_reader.nz):
                for ny in range(config.structured_list_reader.ny):
                    for nx in range(config.structured_list_reader.nx):
                        read_value = reading_file.readline().split()[0]
                        p = np.array([config.structured_list_reader.ox + nx * config.structured_list_reader.dx,
                                      config.structured_list_reader.oy + ny * config.structured_list_reader.dy,
                                      config.structured_list_reader.oz + nz * config.structured_list_reader.dz,
                                      ])  # Position vector
                        _temp_array.append(np.append(p, read_value))
                        # idx = nx + config.structured_list_reader.nx * ny + config.structured_list_reader.nx * config.structured_list_reader.ny * nz + config.structured_list_reader.header_offset
                        # _temp_array.append(np.array())
        grain_array = pd.DataFrame(_temp_array, columns=["x", "y", "z", "v"])
        # grain_array[grain_array["v"] < config.structured_list_reader.min_value] = config.structured_list_reader.min_value
        self.data = grain_array

    def read_header(self):
        """Placeholder for structured list header parsing.

        Category: reader
        Tags: structured-list, header, placeholder
        Usage: subclasses or future readers need to implement header extraction.

        Returns:
            None: current implementation does nothing.
        """
        pass


    def get_data(self) -> np.ndarray:
        """Return structured list data as a numpy array.

        Category: reader
        Tags: structured-list, data, numpy, coordinates
        Usage: scripts need x,y,z,value rows for downstream interpolation or export.

        Returns:
            numpy.ndarray: data values as float array.
        """
        return self.data.values.astype(np.float)

    @property
    def coordinates(self):
        """Return coordinate columns as a numpy array.

        Category: reader
        Tags: structured-list, coordinates, numpy
        Usage: scripts need point coordinates from the structured list.

        Returns:
            numpy.ndarray: coordinate values.
        """
        return self.data[["x", "y", "x"]].values.astype(np.float)

    @property
    def values(self):
        """Return structured list scalar values.

        Category: reader
        Tags: structured-list, values, numpy
        Usage: scripts need the scalar value column only.

        Returns:
            numpy.ndarray: value column.
        """
        return self.data[["v"]].values.astype(np.float)

    def build_info(self):
        """Store metadata about the loaded structured list data.

        Category: reader
        Tags: structured-list, metadata, info
        Usage: downstream writers or tools need source filename and variable-position metadata.

        Returns:
            None: updates info["reader"].
        """
        self.info["reader"] = {"n_cells": self.data.shape[0],
                     "filename": self.filename,
                     "var_name": self.var_name,
                     "var_position": self.var_pos}

    def dump_to_csv(self, output_file, delimiter=","):
        """Write structured list data to CSV.

        Category: writer
        Tags: structured-list, csv, export, coordinates
        Usage: scripts need a plain text artifact with x,y,z,value rows.

        Returns:
            None: writes the CSV file.
        """
        print(f"Starting dump into {output_file}")
        np.savetxt(output_file, self.get_data(), delimiter=delimiter)
        print(f"The data has been properly exported to the {output_file} file")
