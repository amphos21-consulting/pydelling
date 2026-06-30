"""
Feflow reader class
========================

This module allows the user to read the Feflow output files.

The module contains the following fuctions:

-`read_field_dat(filename)` - Reads .dat files
-`compute_diff_2fields(field1, field2, key="Concentration")` - Compute the difference between two fields
-`set_head_bc(sea_rise, z_coord, rho_seawater=1025.0, rho_fresh=1000.0)` - Sets the BC head


"""
import logging
import pandas as pd
import matplotlib.pyplot as plt
logger = logging.getLogger(__name__)


class FeflowBaseRader:
    """Base class for FEFLOW readers.

    Category: FEFLOW reader.
    Tags: feflow, reader, base-class.
    Use when: an MCP agent needs the common parent type used by FEFLOW reader
        implementations before selecting concrete parsing helpers.
    """

    def __init__(self):
        logger.info(f"Feflow reader")
        pass

    def read(self):
        """Placeholder entry point for concrete FEFLOW readers.

        Category: FEFLOW reader.
        Tags: feflow, reader, abstract-method.
        Use when: checking the base API contract before calling subclass
            parsing methods such as ``read_field_dat``.
        Returns:
            None: Base implementation does not read a file.
        """
        pass


class FeflowReader(FeflowBaseRader):
    """Read and post-process simple FEFLOW point-data exports.

    Category: FEFLOW reader.
    Tags: feflow, dat, point-data, concentration, plotting.
    Use when: an MCP agent needs to parse FEFLOW ``.dat`` exports, compare two
        fields, or plot node values.

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
        """Read selected columns from a FEFLOW ``.dat`` file.

        Category: FEFLOW reader.
        Tags: feflow, dat, pandas, point-data.
        Use when: converting a FEFLOW text export into a dictionary of NumPy
            arrays keyed by pydelling-friendly labels.
        Args:
            path_dat: Path to the whitespace-delimited FEFLOW ``.dat`` file.
            keys: Source column names to extract from the file.
            k_labels: Output dictionary keys corresponding to ``keys``.
        Returns:
            dict: Mapping of output labels to NumPy arrays.
        """
        field = {}
        df = pd.read_csv(path_dat, delimiter=r"\s+")

        for ik, key in enumerate(keys):
            field[k_labels[ik]] = df[key].to_numpy()
        return field

    def compute_diff_2fields(self, field1, field2, key="Concentration"):
        """Compute the difference between one variable in two FEFLOW fields.

        Category: FEFLOW reader.
        Tags: feflow, difference, concentration, point-data.
        Use when: comparing baseline and scenario FEFLOW outputs.
        Args:
            field1: First field dictionary, usually from ``read_field_dat``.
            field2: Second field dictionary with the same ``key`` array.
            key: Variable name to subtract.
        Returns:
            dict: Copy of ``field1`` without ``key`` and with a ``"Diff"``
            entry equal to ``field1[key] - field2[key]``.
        """
        diff_field = field1.copy()
        del diff_field[key]
        diff_field["Diff"] = field1[key] - field2[key]
        return diff_field

    def plot_point_data(self, field, key="Concentration"):
        """Create a scatter plot for a FEFLOW point-data field.

        Category: FEFLOW reader.
        Tags: feflow, plot, scatter, concentration, matplotlib.
        Use when: an MCP workflow needs a quick visual diagnostic of field
            values in x/y space.
        Args:
            field: Field dictionary containing ``"x"``, ``"y"``, and ``key``.
            key: Field variable to use as point color.
        Returns:
            matplotlib.figure.Figure: Figure containing the scatter plot.
        """
        fig, ax = plt.subplots()
        sc = ax.scatter(field["x"], field["y"], s=4, c=field[key], cmap="Spectral")
        plt.colorbar(sc, label="Concentration [mg/L]")
        return fig

    def set_head_bc(self, sea_rise, z_coord, rho_seawater=1025.0, rho_fresh=1000.0):
        """Compute density-corrected head boundary conditions.

        Category: FEFLOW reader.
        Tags: feflow, boundary-condition, head, density, seawater.
        Use when: setting sea-level head values for density-driven FEFLOW
            simulations.
        Args:
            sea_rise: Sea-level rise or imposed sea head value.
            z_coord: Elevation coordinate used in the density correction.
            rho_seawater: Seawater density.
            rho_fresh: Freshwater density.
        Returns:
            float: Density-corrected hydraulic head.
        """
        rho_s = rho_seawater
        rho_f = rho_fresh
        return sea_rise * (rho_s / rho_f) - ((rho_s - rho_f) / rho_f) * z_coord


if __name__ == "__main__":
    reader = FeflowReader()
