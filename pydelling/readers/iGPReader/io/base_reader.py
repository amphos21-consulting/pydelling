"""Base class for the different reader subclasses"""

from typing import Dict

import pandas as pd
from copy import deepcopy


class BaseReader:
    """Base iGP reader interface with copy support.

    Category: iGP reader.
    Tags: igp, reader, dataframe, copy.
    Use when: an MCP agent needs the common contract for iGP reader subclasses
        that populate keyed pandas DataFrames.
    """

    filename: str
    data: Dict[str, pd.DataFrame]

    def read(self):
        """This function should read the data automatically from the config file"""
        pass

    def copy(self):
        """This function returns a copy of the reader"""
        return deepcopy(self)
