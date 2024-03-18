""" Feflow reader class
========================

This module allows the user to read the Feflow output files.

The module contains the following fuctions:

-`read_field_dat(filename)` - Reads .dat files

"""
import logging
import pandas as pd
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


if __name__ == "__main__":
    reader = FeflowReader()




