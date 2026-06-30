"""Sparse data interpolation onto PFLOTRAN-compatible meshes.


"""
import logging

import numpy as np
from scipy.interpolate import griddata

from pydelling.utils.decorators import set_run
from .base_interpolator import BaseInterpolator

logger = logging.getLogger(__name__)


class SparseDataInterpolator(BaseInterpolator):
    """Interpolate sparse observations onto a target mesh.

    Category: interpolation.
    Tags: sparse-data, griddata, mesh, pointwise, scipy.
    Use when: to map sparse xyz/value observations onto a
        target mesh using SciPy interpolation.
    """

    divide_over_direction = None
    @set_run
    def run(self, method: str = 'nearest', divide_over_direction=None, **kwargs) -> np.ndarray:
        """Interpolate sparse source values onto the configured mesh.

        Category: interpolation.
        Tags: sparse-data, griddata, mesh, scipy.
        Use when: generating mesh-aligned values from sparse observations.
        Args:
            method: SciPy ``griddata`` interpolation method.
            divide_over_direction: If truthy, split source and target data into
                x-minus/x-plus chunks before interpolating.
            **kwargs: Extra options forwarded to ``scipy.interpolate.griddata``.
        Returns:
            np.ndarray: Mesh coordinates concatenated with interpolated values.
        Side effects:
            Sets ``self.interpolated_data`` and marks the interpolator as run via
            the ``set_run`` decorator.
        """
        if not divide_over_direction:
            logger.info(f"Interpolating data based on {self.info}")
            self.interpolated_data = griddata(self.data[:, 0:-1], self.data[:, -1], self.mesh, method=method, **kwargs)
            return self.get_data()
        else:
            logger.info(f"Dividing data into smaller chunks")
            # Divide the data depending on the given direction
            # For now, only divide in the x direction using the mean value
            mesh_x_plus: np.ndarray = self.mesh[self.mesh[:, 0] >= self.mesh[:, 0].mean()]
            mesh_x_minus: np.ndarray = self.mesh[self.mesh[:, 0] < self.mesh[:, 0].mean()]
            data_x_plus: np.ndarray = self.data[self.data[:, 0] >= self.data[:, 0].mean()]
            data_x_minus: np.ndarray = self.data[self.data[:, 0] < self.data[:, 0].mean()]
            # Interpolate the data
            interpolate_plus = griddata(data_x_plus[:, 0:-1], data_x_plus[:, -1], mesh_x_plus, method=method, **kwargs)
            interpolate_minus = griddata(data_x_minus[:, 0:-1], data_x_minus[:, -1], mesh_x_minus, method=method, **kwargs)
            # Combine the data
            self.interpolated_data = np.concatenate((interpolate_plus, interpolate_minus), axis=0)
            return self.get_data()


    def get_data(self) -> np.ndarray:
        """Return mesh coordinates concatenated with interpolated values.

        Category: interpolation.
        Tags: sparse-data, mesh, interpolated-values.
        Use when: downstream writers need x/y/z coordinates plus the
            interpolated value column.
        Returns:
            np.ndarray: ``self.mesh`` with interpolated values appended.
        """
        temp_array = np.reshape(self.interpolated_data, (self.interpolated_data.shape[0], 1))
        return np.concatenate((self.mesh, temp_array), axis=1)

    def change_min_value(self, min_value=None) -> np.ndarray:
        """Clamp interpolated values below a minimum threshold.

        Category: interpolation.
        Tags: sparse-data, clamp, minimum, postprocess.
        Use when: enforcing a lower bound on interpolated physical properties.
        Args:
            min_value: Lower bound assigned to all smaller interpolated values.
        Returns:
            np.ndarray: Mutated interpolated data array.
        Side effects:
            Updates ``self.interpolated_data`` in place.
        """
        logger.info(f"Equaling values <{min_value} to {min_value}")
        self.interpolated_data[self.interpolated_data < min_value] = min_value
        return self.interpolated_data


    def plot_regular_mesh(self):
        """Prepare a regular-mesh plot after interpolation.

        Category: interpolation.
        Tags: sparse-data, plot, regular-mesh.
        Use when: visualizing interpolated data on a regular target mesh.
        Raises:
            AssertionError: If interpolation has not run or no regular mesh is
                available.
        """
        assert self.is_run, "The interpolator has not been run"
        assert self.has_regular_mesh, "The interpolator has not been run with a regular mesh"
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        plot_data = self.get_data()


    def generate_pointwise_data(self) -> np.ndarray:
        """Return pointwise mesh data with interpolated values appended.

        Category: interpolation.
        Tags: sparse-data, pointwise, export.
        Use when: preparing interpolated data for CSV or pointwise downstream
            tools.
        Returns:
            np.ndarray: Mesh rows plus one interpolated value column.
        Raises:
            AssertionError: If interpolation has not run or no regular mesh is
                available.
        """
        assert self.is_run, "The interpolator has not been run"
        assert self.has_regular_mesh, "The interpolator has not been run with a regular mesh"
        mesh_data = self.mesh.copy()
        mesh_data = np.hstack((mesh_data, np.reshape(self.interpolated_data, (-1, 1))))
        return mesh_data

    def export_pointwise_data(self, output_file='pointwise_data.csv'):
        """Export pointwise interpolated data to CSV.

        Category: interpolation.
        Tags: sparse-data, pointwise, csv, export.
        Use when: writing interpolated mesh values for external tools.
        Args:
            output_file: Destination CSV filename.
        Side effects:
            Writes pointwise data with ``x,y,value`` header.
        """
        assert self.is_run, "The interpolator has not been run"
        assert self.has_regular_mesh, "The interpolator has not been run with a regular mesh"
        mesh_data = self.generate_pointwise_data()
        np.savetxt(output_file, mesh_data, delimiter=',', header='x,y,value')
