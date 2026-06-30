"""
Module documentation.


"""

import logging
import os
from pathlib import Path

import h5py
import numpy as np

from .base_writer import BaseWriter

logger = logging.getLogger(__name__)

class HDF5CentroidWriter(BaseWriter):
    """Write centroid-aligned datasets to PFLOTRAN-style HDF5 files.

    Category: HDF5 writer.
    Tags: hdf5, centroid, cell-ids, permeability, tensor.
    Use when: to export cell-wise scalar, anisotropic, or
        tensor datasets with one-based ``Cell Ids``.
    """

    def run(self, filename=None, remove_if_exists=True, include_cell_id=True):
        """Write the configured dataset to an HDF5 file.

        Category: HDF5 writer.
        Tags: hdf5, centroid, dataset, cell-ids.
        Use when: exporting ``self.data`` under ``self.var_name`` with optional
            PFLOTRAN cell ids.
        Args:
            filename: Optional output filename overriding ``self.filename``.
            remove_if_exists: Whether to remove an existing output file first.
            include_cell_id: Whether to create a one-based ``Cell Ids`` dataset.
        Side effects:
            Creates or overwrites the HDF5 file and writes datasets when
            ``check_data`` succeeds.
        """
        if filename is not None:
            self.filename = filename
        if remove_if_exists:
            try:
                os.remove(self.filename)
            except FileNotFoundError as ef:
                print("Nothing to overwrite!")

        if self.check_data():
            if not os.path.exists(self.filename):
                h5temp = h5py.File(self.filename, "w")
                h5temp.close()
            with h5py.File(self.filename, "r+") as h5temp:
                h5temp.create_dataset(self.var_name, data=self.data)
                if include_cell_id:
                    cell_id = np.array([index + 1 for index in range(len(self.data))])
                    h5temp.create_dataset("Cell Ids", data=cell_id)
        else:
            print("Couldn't find data to dump!")

    def write_anisotropic_dataset(self,
                                  dataset_x,
                                  dataset_y,
                                  dataset_z,
                                  filename=None,
                                  remove_if_exists=True,
                                  var_name=None,
                                  ):
        """Write directional X/Y/Z datasets to HDF5.

        Category: HDF5 writer.
        Tags: hdf5, anisotropic, permeability, cell-ids.
        Use when: exporting anisotropic cell-wise properties for PFLOTRAN-style
            inputs.
        Args:
            filename: name of the file
            dataset_x: dataset containing data in the x-direction
            dataset_y: dataset containing data in the y-direction
            dataset_z: dataset containing data in the z-direction
            remove_if_exists: removes file if exists
            var_name: Optional dataset name prefix overriding ``self.var_name``.
        Side effects:
            Creates ``<var>X``, ``<var>Y``, ``<var>Z``, and ``Cell Ids``
            datasets.
        """
        filename_path = Path(filename if filename else self.filename)
        logger.info(f"Writing anisotropic permeability to {filename_path}")
        if remove_if_exists:
            if filename_path.exists():
                filename_path.unlink()
        with h5py.File(filename_path, "w") as h5_temp:
            var_name_write = var_name if var_name else self.var_name
            h5_temp.create_dataset(f"{var_name_write}X", data=dataset_x)
            h5_temp.create_dataset(f"{var_name_write}Y", data=dataset_y)
            h5_temp.create_dataset(f"{var_name_write}Z", data=dataset_z)
            cell_id = np.array([index + 1 for index in range(len(dataset_x))])
            h5_temp.create_dataset("Cell Ids", data=cell_id)

    def write_full_tensor_dataset(self,
                                  dataset_x,
                                  dataset_xy,
                                  dataset_xz,
                                  dataset_y,
                                  dataset_yz,
                                  dataset_z,
                                  filename=None,
                                  remove_if_exists=True,
                                  var_name=None,
                                  ):
        """Write full tensor component datasets to HDF5.

        Category: HDF5 writer.
        Tags: hdf5, tensor, permeability, cell-ids.
        Use when: exporting full tensor cell-wise properties with X, XY, XZ, Y,
            YZ, and Z components.
        Args:
            filename: name of the file
            dataset_x: dataset containing data in the x-direction
            dataset_xy: dataset containing data in the xy-direction
            dataset_xz: dataset containing data in the xz-direction
            dataset_y: dataset containing data in the y-direction
            dataset_yz: dataset containing data in the yz-direction
            dataset_z: dataset containing data in the z-direction
            remove_if_exists: removes file if exists
            var_name: Optional dataset name prefix overriding ``self.var_name``.
        Side effects:
            Creates tensor component datasets and ``Cell Ids``.
        """
        filename_path = Path(filename if filename else self.filename)
        logger.info(f"Writing full tensor permeability to {filename_path}")
        if remove_if_exists:
            if filename_path.exists():
                filename_path.unlink()
        with h5py.File(filename_path, "w") as h5_temp:
            var_name_write = var_name if var_name else self.var_name
            h5_temp.create_dataset(f"{var_name_write}X", data=dataset_x)
            h5_temp.create_dataset(f"{var_name_write}XY", data=dataset_xy)
            h5_temp.create_dataset(f"{var_name_write}XZ", data=dataset_xz)
            h5_temp.create_dataset(f"{var_name_write}Y", data=dataset_y)
            h5_temp.create_dataset(f"{var_name_write}YZ", data=dataset_yz)
            h5_temp.create_dataset(f"{var_name_write}Z", data=dataset_z)
            cell_id = np.array([index + 1 for index in range(len(dataset_x))])
            h5_temp.create_dataset("Cell Ids", data=cell_id)


    def write_dataset(self,
                      dataset,
                      filename=None,
                      remove_if_exists=True,
                      var_name=None,
                      ):
        """Write one isotropic dataset to HDF5.

        Category: HDF5 writer.
        Tags: hdf5, isotropic, dataset, cell-ids.
        Use when: exporting one scalar value per cell with one-based cell ids.
        Args:
            filename: name of the file
            dataset: output dataset
            remove_if_exists: removes file if exists
            var_name: Optional dataset name overriding ``self.var_name``.
        Side effects:
            Creates the scalar dataset and ``Cell Ids``.
        """
        filename_path = Path(filename if filename else self.filename)
        logger.info(f"Writing anisotropic permeability to {filename_path}")
        if remove_if_exists:
            if filename_path.exists():
                filename_path.unlink()
        with h5py.File(filename_path, "w") as h5_temp:
            var_name_write = var_name if var_name else self.var_name
            h5_temp.create_dataset(f"{var_name_write}", data=dataset)
            cell_id = np.array([index + 1 for index in range(len(dataset))])
            h5_temp.create_dataset("Cell Ids", data=cell_id)
