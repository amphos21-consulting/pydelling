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
    Usage: to map sparse xyz/value observations onto a
        target mesh using SciPy interpolation.
    """

    divide_over_direction = None
    @set_run
    def run(self, method: str = 'nearest', divide_over_direction=None, **kwargs) -> np.ndarray:
        """Interpolate sparse source values onto the configured mesh.

        Category: interpolation.
        Tags: sparse-data, griddata, mesh, scipy.
        Usage: generating mesh-aligned values from sparse observations.
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
        self._invalidate_results()
        self._validate_interpolation_inputs()
        if divide_over_direction not in (None, False, True, "x"):
            raise ValueError("divide_over_direction currently supports only True or 'x'")

        if not divide_over_direction:
            logger.info(f"Interpolating data based on {self.info}")
            self.interpolated_data = np.asarray(
                griddata(
                    self.data[:, 0:-1],
                    self.data[:, -1],
                    self.mesh,
                    method=method,
                    **kwargs,
                )
            ).reshape(-1)
            return self.get_data()
        else:
            logger.info("Dividing data into smaller chunks")
            # Divide the data depending on the given direction
            # For now, only divide in the x direction using the mean value
            dividing_coordinate = self.data[:, 0].mean()
            mesh_plus_mask = self.mesh[:, 0] >= dividing_coordinate
            mesh_minus_mask = ~mesh_plus_mask
            data_plus_mask = self.data[:, 0] >= dividing_coordinate
            data_minus_mask = ~data_plus_mask
            if not data_plus_mask.any() or not data_minus_mask.any():
                raise ValueError("cannot divide interpolation data into two non-empty x chunks")
            # Interpolate the data
            self.interpolated_data = np.empty(self.mesh.shape[0], dtype=float)
            if mesh_plus_mask.any():
                self.interpolated_data[mesh_plus_mask] = np.asarray(
                    griddata(
                        self.data[data_plus_mask, 0:-1],
                        self.data[data_plus_mask, -1],
                        self.mesh[mesh_plus_mask],
                        method=method,
                        **kwargs,
                    )
                ).reshape(-1)
            if mesh_minus_mask.any():
                self.interpolated_data[mesh_minus_mask] = np.asarray(
                    griddata(
                        self.data[data_minus_mask, 0:-1],
                        self.data[data_minus_mask, -1],
                        self.mesh[mesh_minus_mask],
                        method=method,
                        **kwargs,
                    )
                ).reshape(-1)
            return self.get_data()

    def _validate_interpolation_inputs(self):
        if self.data.size == 0:
            raise ValueError("interpolation data must be provided before interpolation")
        if self.mesh.size == 0:
            raise ValueError("mesh data must be provided before interpolation")
        coordinate_dimensions = self.data.shape[1] - 1
        if self.mesh.shape[1] != coordinate_dimensions:
            raise ValueError(
                "interpolation data and mesh coordinate dimensions must match "
                f"({coordinate_dimensions} != {self.mesh.shape[1]})"
            )
        if not np.isfinite(self.data).all():
            raise ValueError("interpolation coordinates and values must be finite")
        if not np.isfinite(self.mesh).all():
            raise ValueError("mesh coordinates must be finite")


    def get_data(self) -> np.ndarray:
        """Return mesh coordinates concatenated with interpolated values.

        Category: interpolation.
        Tags: sparse-data, mesh, interpolated-values.
        Usage: downstream writers need x/y/z coordinates plus the
            interpolated value column.
        Returns:
            np.ndarray: ``self.mesh`` with interpolated values appended.
        """
        if self.interpolated_data.size == 0:
            raise RuntimeError("the interpolation has not been run with the current inputs")
        temp_array = np.reshape(self.interpolated_data, (self.interpolated_data.shape[0], 1))
        return np.concatenate((self.mesh, temp_array), axis=1)

    def change_min_value(self, min_value=None) -> np.ndarray:
        """Clamp interpolated values below a minimum threshold.

        Category: interpolation.
        Tags: sparse-data, clamp, minimum, postprocess.
        Usage: enforcing a lower bound on interpolated physical properties.
        Args:
            min_value: Lower bound assigned to all smaller interpolated values.
        Returns:
            np.ndarray: Mutated interpolated data array.
        Side effects:
            Updates ``self.interpolated_data`` in place.
        """
        if self.interpolated_data.size == 0:
            raise RuntimeError("the interpolation has not been run with the current inputs")
        if isinstance(min_value, (bool, np.bool_)):
            raise ValueError("min_value must be a finite numeric threshold")
        try:
            min_value = float(min_value)
        except (TypeError, ValueError) as error:
            raise ValueError("min_value must be a finite numeric threshold") from error
        if not np.isfinite(min_value):
            raise ValueError("min_value must be a finite numeric threshold")
        logger.info(f"Setting values below {min_value} to {min_value}")
        self.interpolated_data[self.interpolated_data < min_value] = min_value
        return self.interpolated_data


    def plot_regular_mesh(self):
        """Prepare a regular-mesh plot after interpolation.

        Category: interpolation.
        Tags: sparse-data, plot, regular-mesh.
        Usage: visualizing interpolated data on a regular target mesh.
        Raises:
            AssertionError: If interpolation has not run or no regular mesh is
                available.
        """
        self._require_results()
        if not self.has_regular_mesh:
            raise RuntimeError("the interpolator does not have a regular mesh")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        interpolation = self.info["interpolation"]
        n_x = interpolation["n_x"]
        n_y = interpolation["n_y"]
        grid_x = self.mesh[:, 0].reshape(n_y, n_x)
        grid_y = self.mesh[:, 1].reshape(n_y, n_x)
        values = self.interpolated_data.reshape(n_y, n_x)
        plot = ax.pcolormesh(grid_x, grid_y, values, shading="auto")
        fig.colorbar(plot, ax=ax)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        return ax


    def generate_pointwise_data(self) -> np.ndarray:
        """Return pointwise mesh data with interpolated values appended.

        Category: interpolation.
        Tags: sparse-data, pointwise, export.
        Usage: preparing interpolated data for CSV or pointwise downstream
            tools.
        Returns:
            np.ndarray: Mesh rows plus one interpolated value column.
        Raises:
            AssertionError: If interpolation has not run or no regular mesh is
                available.
        """
        self._require_results()
        if not self.has_regular_mesh:
            raise RuntimeError("the interpolator does not have a regular mesh")
        mesh_data = self.mesh.copy()
        mesh_data = np.hstack((mesh_data, np.reshape(self.interpolated_data, (-1, 1))))
        return mesh_data

    def export_pointwise_data(self, output_file='pointwise_data.csv'):
        """Export pointwise interpolated data to CSV.

        Category: interpolation.
        Tags: sparse-data, pointwise, csv, export.
        Usage: writing interpolated mesh values for external tools.
        Args:
            output_file: Destination CSV filename.
        Side effects:
            Writes pointwise data with ``x,y,value`` header.
        """
        self._require_results()
        if not self.has_regular_mesh:
            raise RuntimeError("the interpolator does not have a regular mesh")
        mesh_data = self.generate_pointwise_data()
        np.savetxt(output_file, mesh_data, delimiter=',', header='x,y,value')
