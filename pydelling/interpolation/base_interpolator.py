"""Base class and utilities for interpolation implementations.


"""
import logging

import h5py
import numpy as np
import pandas as pd
import seaborn as sns

from pydelling.config import config
from pydelling.utils.decorators import set_run
from pydelling.writers.base_writer import BaseWriter

logger = logging.getLogger(__name__)


class BaseInterpolator:
    """Base class for interpolating point data onto mesh locations.

    Category: interpolation
    Tags: interpolation, mesh, hdf5, csv, writer
    Usage: implementing interpolation algorithms that share data loading, mesh setup, and export helpers.
    """
    def __init__(self,
                 interpolation_data=None,
                 mesh_data=None):
        """
        Initialize interpolation and mesh containers.
        
        Args:
            interpolation_data (Any): Description.
            mesh_data (Any): Description.
        """
        self.data = np.array([])
        self.mesh = np.array([])
        self.id_data = np.array([])
        self.info = {"interpolation": {}}
        self.interpolated_data = np.array([])
        self.is_run = False
        self.has_regular_mesh = False
        self.filename = None
        if interpolation_data is not None:
            self.add_data(data=interpolation_data)
        if mesh_data is not None:
            self.add_mesh(data=mesh_data)

    def add_data(self, data):
        """Add source data used for interpolation.

        Category: interpolation
        Tags: interpolation, source-data, numpy
        Usage: scripts need to append sample points or values before running interpolation.

        Returns:
            None: appends data to the source data array.
        """
        data = self._as_2d_array(data, "interpolation data")
        if data.shape[1] < 2:
            raise ValueError(
                "interpolation data must contain at least one coordinate and one value column"
            )
        if self.data.size == 0:
            self.data = data.copy()
        else:
            if data.shape[1] != self.data.shape[1]:
                raise ValueError(
                    "new interpolation data must have the same number of columns as existing data"
                )
            self.data = np.vstack((self.data, data))
        self._invalidate_results()

    def add_mesh(self, data, id_index=3):
        """Add target mesh points for interpolation.

        Category: interpolation
        Tags: interpolation, mesh, target-points, ids
        Usage: scripts need to define the coordinates where interpolated values will be evaluated.

        Returns:
            None: appends coordinates and optional id data to the mesh.
        """
        data = self._as_2d_array(data, "mesh data")
        has_ids = data.shape[1] > 3
        if has_ids:
            if not isinstance(id_index, (int, np.integer)) or isinstance(
                id_index, (bool, np.bool_)
            ):
                raise ValueError("id_index must be a valid integer column index")
            if id_index < 0:
                id_index += data.shape[1]
            if id_index < 0 or id_index >= data.shape[1]:
                raise ValueError("id_index is outside the mesh data columns")
            temp_id_data = data[:, id_index]
            coordinate_columns = [
                column for column in range(data.shape[1]) if column != id_index
            ][:3]
            temp_data = data[:, coordinate_columns]
        else:
            temp_data = data

        if self.mesh.size == 0:
            self.mesh = temp_data.copy()
            self.id_data = temp_id_data.copy() if has_ids else np.array([])
        else:
            if temp_data.shape[1] != self.mesh.shape[1]:
                raise ValueError(
                    "new mesh data must have the same coordinate dimensions as the existing mesh"
                )
            if has_ids != bool(self.id_data.size):
                raise ValueError("mesh chunks must consistently include or omit ID columns")
            self.mesh = np.vstack((self.mesh, temp_data))
            if has_ids:
                self.id_data = np.concatenate((self.id_data, temp_id_data))
        self.has_regular_mesh = False
        self._invalidate_results()

    @staticmethod
    def _as_2d_array(data, name):
        array = np.asarray(data)
        if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] == 0:
            raise ValueError(f"{name} must be a non-empty two-dimensional array")
        if not np.issubdtype(array.dtype, np.number):
            raise TypeError(f"{name} must contain numeric values")
        return array

    def _invalidate_results(self):
        self.interpolated_data = np.array([])
        self.is_run = False

    def _require_results(self):
        if not self.is_run or self.interpolated_data.size == 0:
            raise RuntimeError("the interpolation has not been run with the current inputs")

    @set_run
    def run(self):
        """Run the base interpolation placeholder.

        Category: interpolation
        Tags: interpolation, run, mesh, placeholder
        Usage: subclasses need the shared run contract or a simple x-coordinate passthrough.

        Returns:
            numpy.ndarray: interpolated values on the mesh.
        """
        if self.mesh.size == 0:
            raise ValueError("mesh data must be provided before interpolation")
        self.interpolated_data = self.mesh[:, 0].copy()
        return self.interpolated_data

    def get_data(self):
        """Return the interpolated data array.

        Category: interpolation
        Tags: interpolation, data, results
        Usage: scripts need the latest interpolation output for writing or analysis.

        Returns:
            numpy.ndarray: interpolated data.
        """
        return self.interpolated_data

    def dump_to_hdf5(self, filename=None, var_name=None, data=None):
        """Write interpolated data to an HDF5 dataset.

        Category: writer
        Tags: interpolation, hdf5, export, dataset
        Usage: scripts need interpolated values stored in an HDF5 file for downstream models.

        Returns:
            None: creates or updates the requested HDF5 dataset.
        """
        if data is None:
            self._require_results()
            data = self.interpolated_data
        if filename is not None:
            self.filename = filename
        if self.filename is None:
            raise ValueError("filename must be provided for HDF5 export")
        if not var_name:
            raise ValueError("var_name must be provided for HDF5 export")
        with h5py.File(self.filename, "a") as tempfile:
            if var_name in tempfile:
                del tempfile[var_name]
            tempfile.create_dataset(var_name, data=data)

    def dump_to_csv(self, filename=None, **kwargs):
        """Write mesh coordinates and interpolated values to a text file.

        Category: writer
        Tags: interpolation, csv, export, mesh
        Usage: scripts need a tabular artifact containing target coordinates and interpolated values.

        Returns:
            None: writes the text file via numpy.savetxt.
        """
        self._require_results()
        if filename is None:
            raise ValueError("filename must be provided for CSV export")
        temp_array = np.reshape(self.interpolated_data, (self.interpolated_data.shape[0], 1))
        temp_array = np.concatenate((self.mesh, temp_array), axis=1)
        np.savetxt(filename, temp_array, **kwargs)
        if config.general.verbose:
            print(f"Data has been dumped into {filename}")

        # return np.concatenate((self.mesh, temp_array), axis=1)

    def wipe_data(self):
        """Clear source, mesh, and interpolated data arrays.

        Category: interpolation
        Tags: interpolation, reset, data
        Usage: reusing an interpolator for a new dataset.

        Returns:
            None: resets internal data containers.
        """
        self.data = np.array([])
        self.mesh = np.array([])
        self.id_data = np.array([])
        self.interpolated_data = np.array([])
        self.info = {"interpolation": {}}
        self.is_run = False
        self.has_regular_mesh = False

    def write_data(self, writer_class=BaseWriter, filename=None, **kwargs):
        """Persist interpolated data through a writer class.

        Category: writer
        Tags: interpolation, writer, export, data
        Usage: scripts need writer-specific serialization of interpolation results.

        Returns:
            None: instantiates writer_class and runs it.
        """
        self._require_results()
        base_writer = writer_class(filename=filename, data=self.get_data(), info=self.info, **kwargs)
        base_writer.run(filename=filename)

    def remove_output_file(self, writer_class=BaseWriter, filename=None, **kwargs):
        """Remove an output artifact via a writer class.

        Category: writer
        Tags: interpolation, writer, cleanup, output-file
        Usage: scripts need to delete a generated interpolation output.

        Returns:
            None: delegates removal to the writer class.
        """
        base_writer = writer_class(filename=filename, **kwargs)
        base_writer.remove_output_file(filename)

    def get_minmax_coords(self):
        """Compute and store source data x/y bounds.

        Category: interpolation
        Tags: interpolation, bounds, coordinates, metadata
        Usage: regular mesh generation needs source data extents.

        Returns:
            None: stores bounds in attributes and info metadata.
        """
        if self.data.size == 0 or self.data.shape[1] < 3:
            raise ValueError(
                "interpolation data with x, y, and value columns is required"
            )
        self.data_xmin = np.min(self.data[:, 0])
        self.data_xmax = np.max(self.data[:, 0])
        self.data_ymin = np.min(self.data[:, 1])
        self.data_ymax = np.max(self.data[:, 1])
        self.info["interpolation"]["x_min"] = self.data_xmin
        self.info["interpolation"]["x_max"] = self.data_xmax
        self.info["interpolation"]["y_min"] = self.data_ymin
        self.info["interpolation"]["y_max"] = self.data_ymax

    def create_regular_mesh(self, n_x, n_y, dilatation_factor=1.0):
        """Create a regular target mesh from source data extents.

        ``dilatation_factor`` scales both axes about their respective centers.
        A factor of 1 keeps the source bounds, while a factor of 1.1 expands
        the target bounds by 5 percent on each side.  The stored spacing is the
        actual node-to-node spacing of the generated mesh.

        Category: interpolation
        Tags: interpolation, regular-mesh, grid, coordinates
        Usage: scripts need a generated 2D target grid for interpolation.

        Returns:
            None: populates mesh and interpolation metadata.
        """
        if (
            isinstance(n_x, (bool, np.bool_))
            or not isinstance(n_x, (int, np.integer))
            or n_x < 2
        ):
            raise ValueError("n_x must be an integer greater than 1")
        if (
            isinstance(n_y, (bool, np.bool_))
            or not isinstance(n_y, (int, np.integer))
            or n_y < 2
        ):
            raise ValueError("n_y must be an integer greater than 1")
        if isinstance(dilatation_factor, (bool, np.bool_)):
            raise ValueError("dilatation_factor must be a finite number greater than 0")
        try:
            dilatation_factor = float(dilatation_factor)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "dilatation_factor must be a finite number greater than 0"
            ) from error
        if not np.isfinite(dilatation_factor) or dilatation_factor <= 0.0:
            raise ValueError("dilatation_factor must be a finite number greater than 0")

        self.get_minmax_coords()
        x_length = float(self.data_xmax - self.data_xmin)
        y_length = float(self.data_ymax - self.data_ymin)
        if x_length <= 0.0 or y_length <= 0.0:
            raise ValueError("source data must span a non-zero range in both x and y")

        x_center = (self.data_xmin + self.data_xmax) / 2.0
        y_center = (self.data_ymin + self.data_ymax) / 2.0
        dilatated_x_length = x_length * dilatation_factor
        dilatated_y_length = y_length * dilatation_factor
        grid_x_min = x_center - dilatated_x_length / 2.0
        grid_x_max = x_center + dilatated_x_length / 2.0
        grid_y_min = y_center - dilatated_y_length / 2.0
        grid_y_max = y_center + dilatated_y_length / 2.0
        dx = dilatated_x_length / (n_x - 1)
        dy = dilatated_y_length / (n_y - 1)

        self.info["interpolation"].update({"n_x": n_x,
                                           "n_y": n_y,
                                           "dilatation_factor": dilatation_factor,
                                           "type": "regular_mesh",
                                           "d_x": dx,
                                           "d_y": dy,
                                           "grid_x_min": grid_x_min,
                                           "grid_x_max": grid_x_max,
                                           "grid_y_min": grid_y_min,
                                           "grid_y_max": grid_y_max,
                                           })

        linspace_x = np.linspace(grid_x_min, grid_x_max, n_x)
        linspace_y = np.linspace(grid_y_min, grid_y_max, n_y)
        grid_x, grid_y = np.meshgrid(linspace_x, linspace_y)
        self.mesh = np.hstack((grid_x.reshape((grid_x.size, 1)), grid_y.reshape((grid_y.size, 1))))
        self.id_data = np.array([])
        self._invalidate_results()
        self.has_regular_mesh = True

    def describe(self, write_to_file=None, plots=True):
        """Describe interpolated values and optionally plot their distribution.

        Category: interpolation
        Tags: interpolation, statistics, plot, diagnostics
        Usage: scripts need quick QA statistics for interpolation output.

        Returns:
            None: prints statistics, optionally writes CSV and shows a KDE plot.
        """
        self._require_results()
        temp_df = pd.DataFrame(self.interpolated_data)
        logger.info("Describing the interpolated data")
        print(temp_df.describe())
        if write_to_file:
            if type(write_to_file) is str:
                temp_df.describe().to_csv(write_to_file)
            else:
                temp_df.describe().to_csv("interpolated_data-description.csv")
            logger.info("Writing the description to file")
        if plots:
            logger.info("Plotting data")
            import matplotlib.pyplot as plt
            sns.kdeplot(x=self.interpolated_data)
            plt.show()
