"""
This class contains utility functions to use on the PflotranReader class


"""

import numpy as np
import pandas as pd
import h5py

class PflotranProcessingUtils:
    """Provide coordinate and slicing helpers for PFLOTRAN HDF5 output readers.

    Category: reader
    Tags: pflotran, hdf5, coordinates, slices, centroids
    Use when: scripts need spatial extents, spacing, centroids, or slices from PFLOTRAN grids.
    """
    variables: list
    coordinates: np.ndarray
    data: h5py.File
    # data:
    axis_translator = {
        'x': "x[m]",
        'y': "y[m]",
        'z': "z[m]",
    }

    def get_slice(self, data: np.ndarray, axis: str, index: int) -> np.ndarray:
        """Return a 2D slice from a 3D PFLOTRAN data cube by axis index.

        Category: reader
        Tags: pflotran, slice, array, x, y, z
        Use when: scripts need a plane from a full 3D PFLOTRAN result array.
        Args:
            data: Three-dimensional array ordered as ``x, y, z``.
            axis: Axis to slice, one of ``"x"``, ``"y"``, or ``"z"``.
            index: Integer index along the selected axis.
        Returns:
            np.ndarray: 2D data plane extracted from ``data``.
        Raises:
            AssertionError: If ``data`` is not 3D or ``axis`` is unsupported.
        """
        assert len(data.shape) == 3, "The full data array must be provided"
        assert axis in ['x', 'y', 'z'], "The axis must be x, y, or z"

        if axis == 'x':
            return data[index, :, :]
        elif axis == 'y':
            return data[:, index, :]
        elif axis == 'z':
            return data[:, :, index]

    def get_slice_from_coordinates(self, data: np.ndarray, axis: str, coordinate: float) -> np.ndarray:
        """Return a slice at the grid coordinate nearest to ``coordinate``.

        Category: reader
        Tags: pflotran, slice, coordinates, nearest-neighbor
        Use when: scripts need to request a PFLOTRAN slice by physical
            coordinate instead of array index.
        Args:
            data: Three-dimensional array ordered as ``x, y, z``.
            axis: Axis to slice, one of ``"x"``, ``"y"``, or ``"z"``.
            coordinate: Physical coordinate in meters along the selected axis.
        Returns:
            np.ndarray: Sliced data with the selected axis kept as a singleton
            dimension.
        Raises:
            AssertionError: If ``data`` is not 3D or ``axis`` is unsupported.
        """
        assert len(data.shape) == 3, "The full data array must be provided"
        assert axis in ['x', 'y', 'z'], "The axis must be x, y, or z"

        axis_full = self.axis_translator[axis]
        # Find closes index of coordinate
        index = np.argmin(np.abs(self.coordinates[axis_full] - coordinate))

        if axis == 'x':
            sliced_data = data[index, :, :]
            # Expand the dimension of the axis to match the data
            sliced_data = np.expand_dims(sliced_data, axis=0)
            return sliced_data

        elif axis == 'y':
            sliced_data = data[:, index, :]
            # Expand the dimension of the axis to match the data
            sliced_data = np.expand_dims(sliced_data, axis=1)
            return sliced_data

        elif axis == 'z':
            sliced_data = data[:, :, index]
            # Expand the dimension of the axis to match the data
            sliced_data = np.expand_dims(sliced_data, axis=2)
            return sliced_data


    def get_shape_dimensions(self, data: np.ndarray) -> tuple:
        """Return which Cartesian axes have more than one cell.

        Category: reader
        Tags: pflotran, dimensions, shape, cartesian-grid
        Use when: scripts need to infer whether an array represents a 1D, 2D, or
            3D PFLOTRAN result.
        Args:
            data: Array with dimensions ordered as ``x, y, z``.
        Returns:
            str: Concatenated axis labels with length greater than one, such as
            ``"xy"`` or ``"xyz"``.
        """
        dims = ''
        if data.shape[0] > 1:
            dims += 'x'
        if data.shape[1] > 1:
            dims += 'y'
        if data.shape[2] > 1:
            dims += 'z'
        return dims


    def axis_centroids(self, axis):
        """Return centroid coordinates for the selected PFLOTRAN axis.

        Category: reader
        Tags: pflotran, coordinates, centroids, axis
        Use when: scripts need cell-center coordinates for plotting, sampling,
            or interpolation along a named axis.
        Args:
            axis: Axis selector, one of ``"x"``, ``"y"``, or ``"z"``.
        Returns:
            np.ndarray: Cell centroid coordinates along the selected axis.
        Raises:
            AssertionError: If ``axis`` is unsupported.
        """
        assert axis in ['x', 'y', 'z'], "The axis must be x, y, or z"
        axis = self.axis_translator[axis]
        return np.diff(self.coordinates[axis]) + self.coordinates[axis][0:-1]
    @property
    def x_centroid(self):
        """Return centroid coordinates along the PFLOTRAN x axis.

        Category: reader
        Tags: pflotran, x, centroids, coordinates
        Use when: scripts need cell-center x coordinates for plotting or sampling.

        Returns:
            np.ndarray: x-axis centroid coordinates.
        """
        return np.diff(self.coordinates['x[m]']) + self.coordinates['x[m]'][0:-1]

    @property
    def y_centroid(self):
        """Return centroid coordinates along the PFLOTRAN y axis.

        Category: reader
        Tags: pflotran, y, centroids, coordinates
        Use when: scripts need cell-center y coordinates for plotting or sampling.

        Returns:
            np.ndarray: y-axis centroid coordinates.
        """
        return np.diff(self.coordinates['y[m]']) + self.coordinates['y[m]'][0:-1]

    @property
    def z_centroid(self):
        """Return centroid coordinates along the PFLOTRAN z axis.

        Category: reader
        Tags: pflotran, z, centroids, coordinates
        Use when: scripts need cell-center z coordinates for plotting or sampling.

        Returns:
            np.ndarray: z-axis centroid coordinates.
        """
        return np.diff(self.coordinates['z[m]']) + self.coordinates['z[m]'][0:-1]

    @property
    def x_min(self):
        """Return the minimum x coordinate in the PFLOTRAN grid.

        Category: reader
        Tags: pflotran, x, bounds, minimum
        Use when: scripts need the lower x bound for spatial filtering or summaries.

        Returns:
            float: minimum x coordinate.
        """
        return self.coordinates['x[m]'][0]

    @property
    def x_max(self):
        """Return the maximum x coordinate in the PFLOTRAN grid.

        Category: reader
        Tags: pflotran, x, bounds, maximum
        Use when: scripts need the upper x bound for spatial filtering or summaries.

        Returns:
            float: maximum x coordinate.
        """
        return self.coordinates['x[m]'][-1]

    @property
    def y_min(self):
        """Return the minimum y coordinate in the PFLOTRAN grid.

        Category: reader
        Tags: pflotran, y, bounds, minimum
        Use when: scripts need the lower y bound for spatial filtering or summaries.

        Returns:
            float: minimum y coordinate.
        """
        return self.coordinates['y[m]'][0]

    @property
    def y_max(self):
        """Return the maximum y coordinate in the PFLOTRAN grid.

        Category: reader
        Tags: pflotran, y, bounds, maximum
        Use when: scripts need the upper y bound for spatial filtering or summaries.

        Returns:
            float: maximum y coordinate.
        """
        return self.coordinates['y[m]'][-1]

    @property
    def z_min(self):
        """Return the minimum z coordinate in the PFLOTRAN grid.

        Category: reader
        Tags: pflotran, z, bounds, minimum
        Use when: scripts need the lower z bound for spatial filtering or summaries.

        Returns:
            float: minimum z coordinate.
        """
        return self.coordinates['z[m]'][0]

    @property
    def z_max(self):
        """Return the maximum z coordinate in the PFLOTRAN grid.

        Category: reader
        Tags: pflotran, z, bounds, maximum
        Use when: scripts need the upper z bound for spatial filtering or summaries.

        Returns:
            float: maximum z coordinate.
        """
        return self.coordinates['z[m]'][-1]

    @property
    def x_extent(self):
        """Return the x-axis extent of the PFLOTRAN grid.

        Category: reader
        Tags: pflotran, x, extent, bounds
        Use when: scripts need total grid width along x.

        Returns:
            float: x_max minus x_min.
        """
        return self.x_max - self.x_min

    @property
    def y_extent(self):
        """Return the y-axis extent of the PFLOTRAN grid.

        Category: reader
        Tags: pflotran, y, extent, bounds
        Use when: scripts need total grid width along y.

        Returns:
            float: y_max minus y_min.
        """
        return self.y_max - self.y_min

    @property
    def z_extent(self):
        """Return the z-axis extent of the PFLOTRAN grid.

        Category: reader
        Tags: pflotran, z, extent, bounds
        Use when: scripts need total grid width along z.

        Returns:
            float: z_max minus z_min.
        """
        return self.z_max - self.z_min

    @property
    def x_spacing(self):
        """Return cell spacing intervals along the x axis.

        Category: reader
        Tags: pflotran, x, spacing, coordinates
        Use when: scripts need grid spacing along x.

        Returns:
            np.ndarray: adjacent x-coordinate differences.
        """
        return np.diff(self.coordinates['x[m]'])

    @property
    def y_spacing(self):
        """Return cell spacing intervals along the y axis.

        Category: reader
        Tags: pflotran, y, spacing, coordinates
        Use when: scripts need grid spacing along y.

        Returns:
            np.ndarray: adjacent y-coordinate differences.
        """
        return np.diff(self.coordinates['y[m]'])

    @property
    def z_spacing(self):
        """Return cell spacing intervals along the z axis.

        Category: reader
        Tags: pflotran, z, spacing, coordinates
        Use when: scripts need grid spacing along z.

        Returns:
            np.ndarray: adjacent z-coordinate differences.
        """
        return np.diff(self.coordinates['z[m]'])
