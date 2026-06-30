"""
Class that contains functions to read a rasterized file in .asc format


"""

import logging

import h5py
import numpy as np

from pydelling.config import config
from pydelling.readers.iGPReader.io import BaseReader
from pydelling.readers.iGPReader.utils import get_output_path

logger = logging.getLogger(__name__)


class AscReader(BaseReader):
    """Read, transform, and export ASCII raster grids.

    Category: reader
    Tags: raster, asc, iGP, gridded-data, export
    Usage: scripts need legacy iGPReader support for .asc raster files and PFLOTRAN gridded datasets.
    """

    def __init__(self, filename):
        """Initialize the reader and load an ASC raster file.

        Category: reader
        Tags: raster, asc, open, header, data
        Usage: scripts need an ASC raster parsed into metadata and a numpy grid.

        Returns:
            None: stores file metadata, coordinate meshes, and raster data.
        """
        self.filename = filename
        self.info_dict = {}
        self.opened_file = open(self.filename, "r")
        self.xydata_computed = False
        self.read_header()
        self.build_data_structure()
        self.read_data()
        logger.debug(f"CSV data has been read from {self.filename}")
        logger.debug(f"{self.info_dict}")

    def read_header(self, n_header=6):
        """Parse ASC header key-value metadata.

        Category: reader
        Tags: raster, asc, header, metadata
        Usage: scripts need nrows, ncols, origin, cellsize, and NODATA metadata.

        Returns:
            None: updates info_dict with parsed header values.
        """
        for i in range(0, n_header):
            line = self.opened_file.readline().split()
            self.info_dict[line[0]] = float(line[1])

    def read_data(self):
        """Read raster grid rows from the opened ASC file.

        Category: reader
        Tags: raster, asc, data, grid
        Usage: header metadata is loaded and the remaining file lines contain grid values.

        Returns:
            None: fills the data array.
        """
        for id, line in enumerate(self.opened_file.readlines()):
            self.data[id] = line.split()

    def build_data_structure(self):
        """Create raster data and coordinate arrays from ASC metadata.

        Category: reader
        Tags: raster, asc, coordinates, mesh, numpy
        Usage: scripts need allocated grid storage and x/y coordinate meshes before reading data.

        Returns:
            None: initializes data, x_mesh, and y_mesh.
        """
        assert self.info_dict is not {}
        self.data = np.zeros(shape=(int(self.info_dict["nrows"]), int(self.info_dict["ncols"])))
        x_range = np.arange(self.info_dict["xllcorner"], self.info_dict["nrows"] * self.info_dict["cellsize"],
                            self.info_dict["cellsize"])
        y_range = np.arange(self.info_dict["yllcorner"], self.info_dict["ncols"] * self.info_dict["cellsize"],
                            self.info_dict["cellsize"])
        self.x_mesh, self.y_mesh = np.meshgrid(x_range, y_range)
        self.y_mesh = np.flipud(self.y_mesh)  # To fit into the .asc format criteria

    def rebuild_x_y(self):
        """Rebuild x and y coordinate meshes from current raster metadata.

        Category: preprocessing
        Tags: raster, coordinates, mesh, downsample
        Usage: raster dimensions or cellsize change after downsampling or replacement.

        Returns:
            None: updates x_mesh and y_mesh.
        """
        x_range = np.arange(self.info_dict["xllcorner"], self.info_dict["nrows"] * self.info_dict["cellsize"],
                            self.info_dict["cellsize"])
        y_range = np.arange(self.info_dict["yllcorner"], self.info_dict["ncols"] * self.info_dict["cellsize"],
                            self.info_dict["cellsize"])
        self.x_mesh, self.y_mesh = np.meshgrid(x_range, y_range)

    def dump_to_xydata(self):
        """Flatten raster cells into x,y,value rows.

        Category: reader
        Tags: raster, xydata, flatten, coordinates, values
        Usage: scripts need point samples for CSV, WSV, interpolation, or analysis.

        Returns:
            numpy.ndarray: rows containing x, y, and raster value.
        """
        ndata = int(self.info_dict["nrows"] * self.info_dict["ncols"])
        self.xydata = np.zeros(shape=(ndata, 3))
        x_mesh_flatten = self.x_mesh.flatten()
        y_mesh_flatten = self.y_mesh.flatten()
        for id, data in enumerate(self.data.flatten()):
            self.xydata[id] = (x_mesh_flatten[id], y_mesh_flatten[id], data)
        self.xydata_computed = True
        return self.xydata

    def dump_to_csv(self, output_file):
        """Write raster point samples to CSV.

        Category: writer
        Tags: raster, csv, export, coordinates, values
        Usage: scripts need comma-separated x,y,value rows excluding NODATA cells.

        Returns:
            None: writes the CSV file under the configured output path.
        """
        logger.info(f"Writing into {output_file}")
        if not self.xydata_computed:
            xydata = self.dump_to_xydata()
        else:
            xydata = self.xydata
        f = open(get_output_path() / output_file, "w")
        for data in xydata:
            if float(data[2]) == -9999.0:
                continue
            f.write(f"{data[0]},{data[1]},{data[2]}\n")
        f.close()

    def dump_to_wsv(self, output_file):
        """Write raster point samples as whitespace-separated values.

        Category: writer
        Tags: raster, wsv, export, coordinates, values
        Usage: scripts need plain whitespace-delimited x y value rows.

        Returns:
            None: writes the WSV file.
        """
        logger.info(f"Writing into {output_file}")
        if not self.xydata_computed:
            xydata = self.dump_to_xydata()
        else:
            xydata = self.xydata
        f = open(output_file, "w")
        for data in xydata:
            f.write(f"{data[0]} {data[1]} {data[2]}\n")
        f.close()

    def dump_to_asc(self, output_file):
        """Write the current raster grid to an ASC file.

        Category: writer
        Tags: raster, asc, export, header, grid
        Usage: scripts need to persist modified or downsampled raster data in ASC format.

        Returns:
            None: writes the ASC file.
        """
        logger.info(f"Writing into {output_file}")
        file = open(output_file, "w")
        self.write_asc_header(file)
        self.write_asc_data(file)
        file.close()

    def write_asc_header(self, file):
        # assert isinstance(file, type(open)), "is not a correct file"
        """Write ASC header metadata to an open file handle.

        Category: writer
        Tags: raster, asc, header, metadata
        Usage: emitting an ASC file before writing numeric grid rows.

        Returns:
            None: writes header lines to file.
        """
        for head in self.info_dict:
            file.write(f"{head} {self.info_dict[head]}\n")

    def write_asc_data(self, file):
        """Write raster grid values to an open ASC file handle.

        Category: writer
        Tags: raster, asc, data, grid
        Usage: emitting numeric raster rows after an ASC header.

        Returns:
            None: writes raster rows to file.
        """
        np.savetxt(file, self.data, fmt="%3.2f")

    def export_to_gridded_dataset(self, filename=None, attrs=None):
        """Export ASC raster data to a PFLOTRAN gridded dataset HDF5 file.

        Category: writer
        Tags: raster, pflotran, hdf5, gridded-dataset, export
        Usage: PFLOTRAN inputs need a gridded dataset built from an ASC raster.

        Returns:
            None: writes the HDF5 gridded dataset.
        """
        filename = get_output_path() / filename if filename else get_output_path() / "gridded_dataset.h5"
        growth_factor = config.general.raster_growth_factor if config.general.raster_growth_factor else 1.0
        if config.general.raster_growth_factor:
            logger.warning(f'Scaling the dx and dy values of the gridded dataset by {config.general.raster_growth_factor}')
        with h5py.File(filename, "w") as hdf5_file:
            hdf5_group = hdf5_file.create_group(filename.stem)
            hdf5_dataset = hdf5_group.create_dataset("Data", data=self.data)
            hdf5_group.attrs.create("Dimension", ["XY"], dtype="S3")
            hdf5_group.attrs["Discretization"] = [self.info_dict["cellsize"]*growth_factor, self.info_dict["cellsize"]*growth_factor]
            hdf5_group.attrs["Origin"] = [self.info_dict["xllcorner"], self.info_dict["yllcorner"]]
            hdf5_group.attrs["Cell Centered"] = [True]
            # hdf5_group.attrs["Interpolation Method"] = "STEP"
            # hdf5_group.attrs["Max Buffer Size"] = 1
        logger.info(f"Gridded dataset has been exported at {filename}")

    def change_data(self, data: np.array):
        """Replace the raster data array.

        Category: preprocessing
        Tags: raster, data, numpy, replace
        Usage: scripts need to assign filtered, transformed, or externally computed raster values.

        Returns:
            None: updates the data attribute.
        """
        self.data = data

    def downsample_data(self, slice_factor=2):
        """Downsample the raster by a constant row and column stride.

        Category: preprocessing
        Tags: raster, downsample, cellsize, coordinates
        Usage: scripts need a coarser raster grid with updated dimensions and spacing.

        Returns:
            None: mutates data, metadata, and coordinate meshes.
        """
        self.data = self.data[0::slice_factor, 0::slice_factor]
        self.info_dict["nrows"] = self.data.shape[0]
        self.info_dict["ncols"] = self.data.shape[1]
        self.info_dict["cellsize"] *= slice_factor
        AscReader.rebuild_x_y(self)
        logger.info("Data has been downsampled, these are the new settings:")
        logger.info(f"{self.info_dict}")
