"""
Module documentation.


"""

import os

import h5py
import numpy as np

from .base_writer import BaseWriter

import logging
logger = logging.getLogger(__name__)


class HDF5RasterWriter(BaseWriter):
    """Write raster-like interpolation data to PFLOTRAN-style HDF5 datasets.

    Category: writer
    Tags: hdf5, raster, interpolation, pflotran, gridded-dataset
    Usage: scripts need regular-grid data serialized with Times, Data, and spatial attributes.
    """
    def __init__(self,
                 filename,
                 dataset_name,
                 data=None,
                 times=0.0,
                 attributes=None,
                 interpolation_info=None,
                 n_x=None,
                 n_y=None,
                 x_min=None,
                 x_max=None,
                 y_min=None,
                 y_max=None,
                 dilatation_factor=1.0,
                 **kwargs,
                 ):
        """Initialize the HDF5 raster writer and reshape data if needed.

        Category: writer
        Tags: hdf5, raster, interpolation, regular-mesh
        Usage: scripts have flattened, centroid, or mesh-shaped data that must become an HDF5 raster.

        Returns:
            None: stores metadata, reshapes data, and marks it ready for writing.
        """
        if data is None:
            raise ValueError("data must be provided")
        data = np.asarray(data)

        legacy_info = kwargs.pop("info", None)
        self.info = interpolation_info if interpolation_info is not None else legacy_info
        direct_grid_parameters = (n_x, n_y, x_min, x_max, y_min, y_max)
        if any(parameter is not None for parameter in direct_grid_parameters):
            if not all(
                coordinate is not None for coordinate in (x_min, x_max, y_min, y_max)
            ):
                raise ValueError(
                    "x_min, x_max, y_min, and y_max must all be provided"
                )
            if n_x is None:
                if len(data.shape) == 2:
                    n_x = data.shape[1]
                else:
                    raise ValueError("Could not determine n_x, please provide it")

            if n_y is None:
                if len(data.shape) == 2:
                    n_y = data.shape[0]
                else:
                    raise ValueError("Could not determine n_y, please provide it")
            self._validate_grid_size(n_x, n_y)
            dilatation_factor = self._validate_dilatation_factor(dilatation_factor)
            if x_max <= x_min or y_max <= y_min:
                raise ValueError("x_max and y_max must be greater than x_min and y_min")

            grid_x_min, grid_x_max = self._dilatated_bounds(
                x_min, x_max, dilatation_factor
            )
            grid_y_min, grid_y_max = self._dilatated_bounds(
                y_min, y_max, dilatation_factor
            )
            self.info = {
                "interpolation": {
                    "type": "regular_mesh",
                    "n_x": n_x,
                    "n_y": n_y,
                    "x_min": x_min,
                    "x_max": x_max,
                    "y_min": y_min,
                    "y_max": y_max,
                    "grid_x_min": grid_x_min,
                    "grid_x_max": grid_x_max,
                    "grid_y_min": grid_y_min,
                    "grid_y_max": grid_y_max,
                    "d_x": (grid_x_max - grid_x_min) / (n_x - 1),
                    "d_y": (grid_y_max - grid_y_min) / (n_y - 1),
                    "dilatation_factor": dilatation_factor,
                }
            }

        if self.info is None or "interpolation" not in self.info:
            raise ValueError(
                "interpolation_info or complete regular-grid coordinates must be provided"
            )

        interpolation = self.info["interpolation"]
        self._validate_grid_size(interpolation.get("n_x"), interpolation.get("n_y"))
        interpolation["dilatation_factor"] = self._validate_dilatation_factor(
            interpolation.get("dilatation_factor", 1.0)
        )

        super().__init__(data=data, **kwargs)
        if interpolation.get("type") == "regular_mesh":
            self.data = self._prepare_regular_mesh_data(self.data)
        if self.data is not None:
            self.data_loaded = True
        self.region_name = dataset_name
        self.times = times
        self.attributes = {} if attributes is None else dict(attributes)
        self.filename = filename
        logger.info(f"Created HDF5RasterWriter with filename {filename} and parameters {self.info}")

    @staticmethod
    def _validate_grid_size(n_x, n_y):
        for name, value in (("n_x", n_x), ("n_y", n_y)):
            if (
                isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, np.integer))
                or value < 2
            ):
                raise ValueError(f"{name} must be an integer greater than 1")

    @staticmethod
    def _validate_dilatation_factor(dilatation_factor):
        if isinstance(dilatation_factor, (bool, np.bool_)):
            raise ValueError("dilatation_factor must be a finite number greater than 0")
        try:
            factor = float(dilatation_factor)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "dilatation_factor must be a finite number greater than 0"
            ) from error
        if not np.isfinite(factor) or factor <= 0.0:
            raise ValueError("dilatation_factor must be a finite number greater than 0")
        return factor

    @staticmethod
    def _dilatated_bounds(lower, upper, factor):
        center = (lower + upper) / 2.0
        half_length = (upper - lower) * factor / 2.0
        return center - half_length, center + half_length

    def _prepare_regular_mesh_data(self, data):
        """Normalize supported inputs to PFLOTRAN's ``(x, y, time)`` order."""
        interpolation = self.info["interpolation"]
        n_x = interpolation["n_x"]
        n_y = interpolation["n_y"]
        point_count = n_x * n_y

        if data.ndim == 1:
            if data.size != point_count:
                raise ValueError(
                    f"1D data must contain exactly {point_count} regular-grid values"
                )
            return data.reshape(n_y, n_x).T[:, :, np.newaxis]

        if data.ndim == 2:
            if data.shape == (point_count, 3):
                return data[:, 2].reshape(n_y, n_x).T[:, :, np.newaxis]
            if data.shape == (n_y, n_x):
                return data.T[:, :, np.newaxis]
            if n_x != n_y and data.shape == (n_x, n_y):
                return data[:, :, np.newaxis]
            if data.shape[1] == point_count:
                layers = [layer.reshape(n_y, n_x).T for layer in data]
                return np.moveaxis(np.asarray(layers), 0, -1)
            raise ValueError(
                "2D data must be a y-by-x grid, x-by-y grid, centroid rows, "
                "or time-by-flattened-values"
            )

        if data.ndim == 3:
            if data.shape[1:] == (point_count, 3):
                layers = [layer[:, 2].reshape(n_y, n_x).T for layer in data]
                return np.moveaxis(np.asarray(layers), 0, -1)
            if data.shape[1:] == (n_y, n_x):
                layers = [layer.T for layer in data]
                return np.moveaxis(np.asarray(layers), 0, -1)
            if data.shape[:2] == (n_x, n_y):
                return data
            raise ValueError(
                "3D data must be time-indexed grids, time-indexed centroid rows, "
                "or already use x-by-y-by-time order"
            )

        raise ValueError("regular-grid data must have between one and three dimensions")


    def transform_flatten_to_regular_mesh(self, data):
        """Reshape flattened values into regular mesh layers.

        Category: writer
        Tags: hdf5, raster, reshape, regular-mesh
        Usage: flattened interpolation output needs n_y by n_x grid shape.

        Returns:
            numpy.ndarray: array of regular mesh layers.
        """
        aux_array = []
        if len(data.shape) == 2:
            for case in data:
                aux_array.append(np.reshape(case, (self.info["interpolation"]["n_y"], self.info["interpolation"]["n_x"])).T)
        elif len(data.shape) == 1:
            aux_array.append(np.reshape(data, (self.info["interpolation"]["n_y"], self.info["interpolation"]["n_x"])).T)

        return np.array(aux_array)

    def centroid_transform_to_mesh(self):
        """Transform centroid x,y,value rows into a regular mesh array.

        Category: writer
        Tags: hdf5, raster, centroids, reshape
        Usage: data is stored as centroid rows and needs grid shape.

        Returns:
            numpy.ndarray: reshaped mesh data.
        """
        assert len(self.data.shape) >= 2 and self.data.shape[1] == 3
        _data = self.data[:, 2]
        _data = np.reshape(_data, (self.info["interpolation"]["n_y"], self.info["interpolation"]["n_x"])).T
        return _data

    def _centroid_transform_to_mesh(self, data):
        """Transform one centroid row array into a regular mesh array.

        Category: writer
        Tags: hdf5, raster, centroids, reshape
        Usage: converting one layer of centroid x,y,value data into mesh shape.

        Returns:
            numpy.ndarray: reshaped mesh layer.
        """
        assert len(data.shape) >= 1 and data.shape[1] == 3
        _data = data[:, 2]
        _data = np.reshape(_data, (self.info["interpolation"]["n_y"], self.info["interpolation"]["n_x"])).T
        return _data

    def add_default_attributes(self, hdf5_group: h5py.Dataset):
        """Add PFLOTRAN gridded dataset spatial attributes.

        Category: writer
        Tags: hdf5, raster, attributes, pflotran
        Usage: Data datasets need Dimension, Discretization, Origin, and interpolation metadata.

        Returns:
            None: mutates HDF5 group attributes.
        """
        interpolation = self.info["interpolation"]
        factor = interpolation["dilatation_factor"]
        grid_x_min = interpolation.get("grid_x_min")
        grid_y_min = interpolation.get("grid_y_min")
        if grid_x_min is None:
            grid_x_min, _ = self._dilatated_bounds(
                interpolation["x_min"], interpolation["x_max"], factor
            )
        if grid_y_min is None:
            grid_y_min, _ = self._dilatated_bounds(
                interpolation["y_min"], interpolation["y_max"], factor
            )

        hdf5_group.attrs.create('Dimension', self.attributes['Dimension'] if 'Dimension' in self.attributes else 'XY', dtype="S3")
        hdf5_group.attrs["Discretization"] = [interpolation["d_x"], interpolation["d_y"]]
        hdf5_group.attrs["Origin"] = [grid_x_min, grid_y_min]
        hdf5_group.attrs["Interpolation_Method"] = "STEP"

    def run(self, filename=None):
        """Write the HDF5 raster dataset to disk.

        Category: writer
        Tags: hdf5, raster, export, dataset
        Usage: scripts need a complete HDF5 file with Times, Data, and attributes.

        Returns:
            None: writes or replaces the HDF5 file.
        """
        if filename is not None:
            self.filename = filename

        if self.check_data():
            if not os.path.exists(self.filename):
                h5temp = h5py.File(self.filename, "w")
                h5temp.close()
            else:
                # Delete the file if it exists
                os.remove(self.filename)
                h5temp = h5py.File(self.filename, "w")
                h5temp.close()
            with h5py.File(self.filename, "r+") as h5temp:
                try:
                    temp_group = h5temp.create_group(name=self.region_name)
                except ValueError as e:
                    print(f"ERROR writing HDF5 file: {e}")
                    print("INFO: Possible solution: use remove_output_file(filename=\"\")")
                    exit(1)
                temp_group.create_dataset("Times", data=self.times)
                temp_group.create_dataset("Data", data=self.data)
                # Adds default attributes to the group
                self.add_default_attributes(temp_group)
                # Extends the default attributes to the ones defined by the user
                for attribute, value in self.attributes.items():
                    if attribute != "Dimension":
                        temp_group.attrs[attribute] = value

            logger.info(f"Saved raster file to {self.filename}")
        else:
            print("Couldn't find data to dump!")


    def add_dimension_attribute(self, dimension):
        """Set the HDF5 Dimension attribute value.

        Category: writer
        Tags: hdf5, raster, attributes, dimension
        Usage: scripts need to override the default XY dimension metadata.

        Returns:
            None: updates attributes["Dimension"].
        """
        self.attributes["Dimension"] = dimension
