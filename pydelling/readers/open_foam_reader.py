"""
Base interface for a reader class


"""
import logging

import numpy as np

from pydelling.readers import BaseReader

logger = logging.getLogger(__name__)
import Ofpp
from pydelling.config import config
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class OpenFoamReader(BaseReader):
    """Read OpenFOAM mesh metadata through ``Ofpp.FoamMesh``.

    Category: OpenFOAM reader.
    Tags: openfoam, mesh, cell-centers, cell-volumes, Ofpp.
    Use when: an MCP agent needs to locate OpenFOAM mesh geometry data such as
        cell centers and cell volumes for interpolation or export workflows.
    """

    def __init__(self, filename=None):
        """Create an OpenFOAM reader for a case directory.

        Category: OpenFOAM reader.
        Tags: openfoam, case-directory, initialization.
        Use when: loading an OpenFOAM case from an explicit path or from
            ``config.open_foam_reader.filename``.
        Args:
            filename: OpenFOAM case directory. If omitted, the configured
                default path is used.
        Side effects:
            Instantiates the underlying ``Ofpp.FoamMesh`` through ``open_file``.
        """
        self.filename = Path(filename) if filename else Path(config.open_foam_reader.filename)
        logger.info(f"Reading OpenFOAM mesh file from {self.filename}")
        super().__init__(filename=self.filename)


    def open_file(self, filename):
        """Open an OpenFOAM case as an ``Ofpp.FoamMesh``.

        Category: OpenFOAM reader.
        Tags: openfoam, Ofpp, mesh.
        Use when: reinitializing the reader's mesh object from a case path.
        Args:
            filename: OpenFOAM case directory. The method uses ``self.filename``
                for the actual ``FoamMesh`` construction.
        Side effects:
            Sets ``self.mesh``.
        """
        self.mesh = Ofpp.FoamMesh(self.filename)

    @property
    def cell_centers(self) -> np.array:
        """Return OpenFOAM cell center coordinates.

        Category: OpenFOAM reader.
        Tags: openfoam, cell-centers, coordinates.
        Use when: an MCP workflow needs spatial locations for OpenFOAM cells.
        Returns:
            np.ndarray: Cell center coordinates from the OpenFOAM case.
        Side effects:
            Lazily reads ``0/C`` or ``constant/C`` and toggles the configured
            ``is_cell_centers_read`` flag.
        """
        if not config.globals.is_cell_centers_read:
            try:
                self.mesh.read_cell_centres(str(self.filename / "0/C"))
                logger.info(f"Reading cell center locations from {self.filename / '0/C'}")
                config.globals.is_cell_centers_read = True
            except:
                logger.info(f"Reading cell center locations from {self.filename / 'constant/C'}")
                self.mesh.read_cell_centres(str(self.filename / "constant/C"))
                config.globals.is_cell_centers_read = True

        return self.mesh.cell_centres

    @property
    def cell_volumes(self) -> np.array:
        """Return OpenFOAM cell volumes.

        Category: OpenFOAM reader.
        Tags: openfoam, cell-volumes, mesh.
        Use when: an MCP workflow needs OpenFOAM cell volumes for weighted
            calculations or export.
        Returns:
            np.ndarray: Cell volumes from the OpenFOAM case.
        Side effects:
            Lazily reads ``0/V`` or ``constant/V`` and toggles the configured
            ``is_cell_volumes_read`` flag.
        """
        if not config.globals.is_cell_volumes_read:
            try:
                self.mesh.read_cell_volumes(str(self.filename / "0/V"))
                logger.info(f"Reading cell volume locations from {self.filename / '0/V'}")
                config.globals.is_cell_volumes_read = True
            except:
                logger.info(f"Reading cell volume locations from {self.filename / 'constant/V'}")
                self.mesh.read_cell_volumes(str(self.filename / "constant/V"))
                config.globals.is_cell_volumes_read = True

        return self.mesh.cell_volumes

    def get_data(self) -> np.ndarray:
        """Return the generic reader payload placeholder.

        Category: OpenFOAM reader.
        Tags: openfoam, base-reader, data.
        Use when: code expects the ``BaseReader`` data accessor; use
            ``cell_centers`` or ``cell_volumes`` for actual OpenFOAM geometry
            arrays.
        Returns:
            np.ndarray: Current placeholder zero array.
        """
        return np.array(0)

    def build_info(self):
        """Reset OpenFOAM reader metadata.

        Category: OpenFOAM reader.
        Tags: openfoam, metadata, info.
        Use when: satisfying the ``BaseReader`` metadata hook for OpenFOAM mesh
            cases.
        Side effects:
            Sets ``self.info`` to an empty dictionary.
        """
        self.info = {}
