"""
Centroid file reader


"""
import logging

import numpy as np

from .base_reader import BaseReader

logger = logging.getLogger(__name__)


class StructuredGridReader(BaseReader):
    """Read structured-grid centroid rows and an associated variable.

    Category: structured-grid reader.
    Tags: structured-grid, centroids, variable, csv.
    Use when: an MCP agent needs to load structured-grid coordinate rows and
        combine them with a scalar variable column.
    """

    def __init__(self, filename, var_pos=3, var_name="var", var_type=np.float32, centroid_pos=(0, 3), header=False):
        """Configure structured-grid parsing positions and load the file.

        Category: structured-grid reader.
        Tags: structured-grid, initialization, centroids, variable.
        Use when: constructing a reader for text rows containing centroid
            coordinates and a variable value.
        Args:
            filename: Source text file.
            var_pos: Column index containing the variable value.
            var_name: Logical name of the variable.
            var_type: NumPy dtype used for the variable array.
            centroid_pos: Start/end positions for centroid coordinate columns.
            header: Whether the file contains a leading header line.
        """
        self.var_pos = None
        self.var = None
        self.var_name = None
        self.var_type = None
        self.centroid_pos = None
        self.header = None
        super().__init__(filename, var_pos=var_pos,
                         var_name=var_name,
                         var_type=var_type,
                         centroid_pos=centroid_pos,
                         header=header)

    def read_file(self, opened_file: BaseReader):
        """Parse centroid coordinates and variable values from an open file.

        Category: structured-grid reader.
        Tags: structured-grid, parse, centroids, variable.
        Use when: reading structured-grid text rows into NumPy arrays.
        Args:
            opened_file: Open file handle positioned at data rows.
        Side effects:
            Sets ``self.data`` and ``self.var``.
        """
        temp_centroid = []
        temp_id = []
        for line in opened_file.readlines():
            data_row = line.split()
            temp_centroid.append(data_row[self.centroid_pos[0]:self.centroid_pos[1]])
            temp_id.append([data_row[self.var_pos]])
        self.data = np.array(temp_centroid, dtype=np.float32)
        self.var = np.array(temp_id, dtype=self.var_type)


    def read_header(self):
        """Placeholder for structured-grid header parsing.

        Category: structured-grid reader.
        Tags: structured-grid, header, extension-point.
        Use when: implementing support for structured-grid formats with
            explicit headers.
        Notes:
            The current implementation does not parse header content.
        """
        pass

    def get_data(self) -> np.ndarray:
        """Return centroid coordinates concatenated with variable values.

        Category: structured-grid reader.
        Tags: structured-grid, data, numpy, variable.
        Use when: downstream workflows need one array containing coordinates and
            the parsed variable.
        Returns:
            np.ndarray: ``self.data`` horizontally stacked with ``self.var``.
        """
        return np.hstack((self.data, self.var))

    def build_info(self):
        """Build metadata for the parsed structured-grid file.

        Category: structured-grid reader.
        Tags: structured-grid, metadata, info.
        Use when: MCP tools need cell count, source filename, and variable
            metadata after parsing.
        Side effects:
            Updates ``self.info["reader"]``.
        """
        self.info["reader"] = {"n_cells": self.data.shape[0],
                     "filename": self.filename,
                     "var_name": self.var_name,
                     "var_position": self.var_pos}

    def dump_to_csv(self, output_file, delimiter=","):
        """Write parsed structured-grid data to a delimited text file.

        Category: structured-grid reader.
        Tags: structured-grid, csv, export.
        Use when: exporting loaded structured-grid coordinates and values.
        Args:
            output_file: Destination file path.
            delimiter: Output delimiter.
        Side effects:
            Writes ``self.get_data()`` to ``output_file``.
        """
        print(f"Starting dump into {output_file}")
        np.savetxt(output_file, self.get_data(), delimiter=delimiter)
        print(f"The data has been properly exported to the {output_file} file")
