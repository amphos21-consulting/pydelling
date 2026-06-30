"""
Base interface for a reader class


"""
import logging

import numpy as np

from pydelling.readers import BaseReader

logger = logging.getLogger(__name__)
from pydelling.config import config
import logging
from pathlib import Path
import pandas as pd
logger = logging.getLogger(__name__)
from linecache import getline


class ConnectFlowReader(BaseReader):
    """Read ConnectFlow mesh nodes and expose basic spatial metadata.

    Category: ConnectFlow reader.
    Tags: connectflow, mesh, nodes, bounds, span.
    Usage: to parse ConnectFlow mesh node coordinates and
        reason about their spatial extent.
    """

    def __init__(self, filename=None):
        """Create a reader for a ConnectFlow mesh file.

        Category: ConnectFlow reader.
        Tags: connectflow, mesh, initialization.
        Usage: loading a ConnectFlow mesh from an explicit path or from the
            configured default path.
        Args:
            filename: Path to the ConnectFlow mesh file. If omitted, the
                configured OpenFOAM reader filename is used as the fallback.
        Side effects:
            Calls ``BaseReader`` initialization, which reads the file.
        """
        self.filename = Path(filename) if filename else Path(config.open_foam_reader.filename)
        logger.info(f"Reading ConnectFlow mesh file from {self.filename}")
        super().__init__(filename=self.filename)

    def open_file(self, filename):
        """Parse ConnectFlow header counts and node coordinates.

        Category: ConnectFlow reader.
        Tags: connectflow, mesh, nodes, pandas.
        Usage: loading mesh-node data from a ConnectFlow text file.
        Args:
            filename: ConnectFlow mesh file path.
        Side effects:
            Sets ``n_nodes``, ``n_elements``, ``n_mat``, ``_mesh_nodes``, and
            rebuilt ``info`` metadata.
        """
        filename_string = str(filename)
        header = getline(filename_string, 1).split()
        self.n_nodes = int(header[1])
        self.n_elements = int(header[3])
        self.n_mat = int(header[5])
        with open(filename, "r") as opened_file:
            _nodes = [line.rstrip().split() for line in opened_file.readlines()[2: 2 + self.n_nodes - 1]]
            self._mesh_nodes = pd.DataFrame(np.array(_nodes).astype(np.float), columns=["index", "x", "y", "z"])
            self._mesh_nodes = self.mesh_nodes.set_index("index")
        self.build_info()

    @property
    def mesh_nodes(self) -> pd.DataFrame:
        """Return parsed ConnectFlow mesh nodes.

        Category: ConnectFlow reader.
        Tags: connectflow, mesh, nodes, dataframe.
        Usage: workflows need node ids and x/y/z coordinates as a
            DataFrame.
        Returns:
            pd.DataFrame: Node table indexed by node id.
        Raises:
            AssertionError: If node data has not been parsed.
        """
        assert hasattr(self, "_mesh_nodes"), "Mesh has not been properly assigned"
        return self._mesh_nodes


    def get_data(self) -> np.ndarray:
        """Return the generic reader payload placeholder.

        Category: ConnectFlow reader.
        Tags: connectflow, base-reader, data.
        Usage: code expects the ``BaseReader`` data accessor; use
            ``mesh_nodes`` for actual parsed node coordinates.
        Returns:
            np.ndarray: Current placeholder zero array.
        """
        return np.array(0)


    def build_info(self):
        """Build bounds and span metadata from parsed mesh nodes.

        Category: ConnectFlow reader.
        Tags: connectflow, bounds, span, metadata.
        Usage: an MCP workflow needs the spatial extent of the ConnectFlow
            mesh after parsing.
        Side effects:
            Sets ``self.info["bounds"]`` and ``self.info["span"]`` for x/y/z.
        """
        min_x = self._mesh_nodes["x"].min()
        max_x = self._mesh_nodes["x"].max()
        min_y = self._mesh_nodes["y"].min()
        max_y = self._mesh_nodes["y"].max()
        min_z = self._mesh_nodes["z"].min()
        max_z = self._mesh_nodes["z"].max()
        self.info = {
            "bounds": {
                "x": [min_x, max_x],
                "y": [min_y, max_y],
                "z": [min_z, max_z],
            }
        }
        self.info.update({
            "span": {
                "x": self.info["bounds"]["x"][1] - self.info["bounds"]["x"][0],
                "y": self.info["bounds"]["y"][1] - self.info["bounds"]["y"][0],
                "z": self.info["bounds"]["z"][1] - self.info["bounds"]["z"][0],
            }
        })

    def get_bounds(self):
        """Return x/y/z coordinate bounds.

        Category: ConnectFlow reader.
        Tags: connectflow, bounds, metadata.
        Usage: downstream workflows need minimum and maximum coordinates.
        Returns:
            dict: Bounds dictionary with ``x``, ``y``, and ``z`` entries.
        """
        return self.info["bounds"]


    def get_span(self):
        """Return x/y/z coordinate spans.

        Category: ConnectFlow reader.
        Tags: connectflow, span, metadata.
        Usage: downstream workflows need total mesh extents by axis.
        Returns:
            dict: Span dictionary with ``x``, ``y``, and ``z`` entries.
        """
        return self.info["span"]
