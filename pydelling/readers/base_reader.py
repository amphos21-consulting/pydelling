"""Base interfaces and helpers for file-based readers.


"""
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
import pydelling.utils.sub_fish_module as subfish


class BaseReader:
    """Provide the common interface for pydelling reader classes.

    Category: reader
    Tags: reader, file, data, csv, coordinates
    Use when: scripts need the base contract shared by concrete pydelling file readers.
    """

    data: np.ndarray  # Hint of self.data array
    info: dict
    raw_data: None

    def __init__(self, filename=None,
                 header=False,
                 read_data=True,
                 info=None,
                 data=None,
                 **kwargs,
                 ):
        """
        Set up reader metadata and optionally load data from disk.
        
        Args:
            filename (Any): Description.
            header (Any): Description.
            read_data (Any): Description.
            info (Any): Description.
            data (Any): Description.
            **kwargs (Any): Description.
        """
        self.filename = Path(filename)
        self.info = {"reader": {}}
        self.data = None
        self.header = header
        self.__dict__.update(kwargs)
        if read_data:
            self.open_file(filename, **kwargs)
        else:
            assert data is not None, "Error: data is None"
            # assert info is not None, "Error: info is None"
            self.data = data
            # self.info = info

    def read_file(self, opened_file):
        """
        Reads the data and stores it inside the class
        
        Args:
            opened_file (Any): Description.
        """
        pass

    def open_file(self, filename, **kwargs):
        """Open a file, optionally skip its header, read data, and build metadata.

        Category: reader
        Tags: reader, file, open, data, metadata
        Use when: a concrete reader should load data from disk using its read_file implementation.

        Returns:
            None: updates reader data and info.
        """
        with open(filename) as opened_file:
            if self.header:
                opened_file.readline()  # For now, skips the header if it has
            self.read_file(opened_file)
        self.build_info()

    def read_header(self, opened_file):
        """
        Reads the header of the file
        
        Args:
            opened_file (Any): Description.
        """
        pass

    def get_data(self) -> np.ndarray:
        """Return data loaded by this reader.

        Category: reader
        Tags: reader, data, numpy, array
        Use when: scripts need the numeric payload from a pydelling reader.

        Returns:
            np.ndarray: loaded reader data.
        """
        return np.array(0)

    def build_info(self):
        """
        Generates a dictionary containing the basic info of the read data
        :return:
        """
        self.info = {}

    def global_coords_to_local(self, x_local_to_global, y_local_to_global):
        """
        Converts global data coordinates into local
        
        Args:
            x_local_to_global (Any): Description.
            y_local_to_global (Any): Description.
        """
        assert len(self.data.shape) >= 2 and self.data.shape[1] >= 2, "Error in data shape"
        self.data[:, 0] -= x_local_to_global
        self.data[:, 1] -= y_local_to_global

    def local_coords_to_global(self, x_local_to_global, y_local_to_global):
        """
        Converts local data coordinates into global
        
        Args:
            x_local_to_global (Any): Description.
            y_local_to_global (Any): Description.
        """
        assert len(self.data.shape) >= 2 and self.data.shape[1] >= 2, "Error in data shape"
        self.data[:, 0] += x_local_to_global
        self.data[:, 1] += y_local_to_global

    def dump_to_csv(self, output_file, delimiter=","):
        """Write reader data to a CSV file.

        Category: writer
        Tags: reader, writer, csv, export, data
        Use when: scripts need to export loaded reader data as delimited text.

        Returns:
            None: writes output_file.
        """
        print(f"Starting dump into {output_file}")
        np.savetxt(output_file, self.get_data(), delimiter=delimiter)
        print(f"The data has been properly exported to the {output_file} file")

    def create_postprocess_dict(self):
        """Create a local folder used to store postprocessing artifacts.

        """
        self.postprocessing_dict = Path().cwd() / "postprocess"
        self.postprocessing_dict.mkdir(exist_ok=True)

    def generate_subfish_data(self, subfish_dict: dict, unit_factor=1/(365 * 24), unit_name='d') -> pd.DataFrame:
        """Generate SUBFISH results as a DataFrame from a parameter dictionary.

        Category: reader
        Tags: subfish, dataframe, transport, calculation
        Use when: scripts need tabular SUBFISH output from pydelling reader utilities.

        Returns:
            pd.DataFrame: time and result columns.
        """
        if not subfish_dict:
            raise AttributeError('Please, provide a suitable subfish dict object')
        tang_sol = subfish.calculate_tang(subfish_dict)
        tang_sol[0] *= unit_factor
        tang_sol_pd = pd.DataFrame({f'Time [{unit_name}]': tang_sol[0],
                                    'Result [M]': tang_sol[1]
                                    }
                                   )
        return tang_sol_pd

    @property
    def values(self):
        """Return the loaded data through the common values property.

        Category: reader
        Tags: reader, values, data, array
        Use when: scripts need reader data through a property-style accessor.

        Returns:
            Any: value returned by get_data.
        """
        return self.get_data() 
