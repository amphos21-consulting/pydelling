"""
Module documentation.


"""

import pandas as pd

from pydelling.utils.decorators import set_run


class BasePreprocessing:
    """Base class for preprocessing workflows.

    Category: preprocessing.
    Tags: preprocessing, dataframe, csv, extension-point.
    Usage: to understand the minimal contract for pydelling
        preprocessing classes that load data and expose a ``run`` hook.
    """

    def __init__(self, data: pd.DataFrame = None, filename=None):
        """
        __init__ method.
        
        Args:
            data (pd.DataFrame): Description.
            filename (Any): Description.
        """
        if data is not None:
            self.data = data
        elif filename:
            self.data = pd.read_csv(filename)

    @set_run
    def run(self):
        """
        This method should be implemented for each preprocessing class. It should run the preprocessing algorithm.
        Returns: the result of the preprocessing algorithm
        """
        return 1
