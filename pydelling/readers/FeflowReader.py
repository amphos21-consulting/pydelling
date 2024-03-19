""" Feflow reader class
========================

This module allows the user to read the Feflow output files.

The module contains the following fuctions:

-`read_field_dat(filename)` - Reads .dat files

"""
import logging
import pandas as pd
import matplotlib.pyplot as plt
logger = logging.getLogger(__name__)


class FeflowBaseRader:
    def __init__(self):
        logger.info(f"Feflow reader")
        pass

    def read(self):
        """ Reads method. """
        pass


class FeflowReader(FeflowBaseRader):
    """
    Feflow reader class

    Examples:
        >>> reader = FeflowReader()
    """
    def __init__(self):
        super().__init__()
        pass

    def read_field_dat(self,
                       path_dat,
                       keys=["X", "Y", "Z", "Node", "MINIT"],
                       k_labels=["x", "y", "z", "inode", "Concentration"],
                       ):
        """
        Reads the keys.
        "MINIT" = concentration (feflow notation)

        Parameters
        ----------
        path_dat : String with the path to the .dat file

        keys : List with the headers of .dat to be read.

        k_labels : List with the headers at the vtu file.

        Returns:
        --------
        field: Dictionary with the field.

        """
        field = {}
        df = pd.read_csv(path_dat, delimiter=r"\s+")

        for ik, key in enumerate(keys):
            field[k_labels[ik]] = df[key].to_numpy()
        return field

    def compute_diff_2fields(self, field1, field2, key="Concentration"):
        """
        Computes the differences between two fields.
        Parameters
        ----------
        field1 : Dict with the x, y, z, field values.

        field2 : Dict with the x, y, z, field values.

        key : String with the key to compute the differences

        Returns:
        --------
        diff_field: Dict with the x, y, z, difference field values.

        """
        diff_field = field1.copy()
        del diff_field[key]
        diff_field["Diff"] = field1[key] - field2[key]
        return diff_field

    def plot_point_data(self, field, key="Concentration"):
        """
        Scatter plot of the point data.

        Parameters
        ----------
        field : Dict with the x, y, z, field values.

        key : String with the key to compute the differences

        Returns:
        --------
        fig: Object figure.
        """
        fig, ax = plt.subplots()
        sc = ax.scatter(field["x"], field["y"], s=4, c=field[key], cmap="Spectral")
        plt.colorbar(sc, label="Concentration [mg/L]")
        return fig

    def set_head_bc(self, sea_rise, z_coord, rho_seawater=1025.0, rho_fresh=1000.0):
        """
        Sets the head for the density driven simulations.

        :parameter
        sea_rise : float
            Sea rise in meters
        z_coord : np.array
            Z-coordinates.
        rho_seawater : float
            Density of the seawater in kg/m3
        rho_fresh : float
            Density of the freshwater in kg/m3

        :returns
        head_1 : np.array
            BC head.
        """
        rho_s = rho_seawater
        rho_f = rho_fresh
        return sea_rise * (rho_s / rho_f) - ((rho_s - rho_f) / rho_f) * z_coord


if __name__ == "__main__":
    reader = FeflowReader()

