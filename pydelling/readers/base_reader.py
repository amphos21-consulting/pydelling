"""Base interfaces and helpers for file-based readers.


"""
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
import pydelling.utils.sub_fish_module as subfish


class BaseReader:
    """Base interface shared by data reader implementations.

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
        """
        Open a file handle, parse data, and refresh metadata.
        
        Args:
            filename (Any): Description.
            **kwargs (Any): Description.
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
        """
        Outputs the read data
        :return:
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
        """
        Writes the data into a csv file
        
        Args:
            output_file (Any): Description.
            delimiter (Any): Description.
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
        """
        This method reads a given subfish dict and returns the calculated results
        Args:
            subfish_dict: dictionary containing subfish module parameters
            unit_factor: factor multiplyin the results (originally computed in seconds)
        Returns:
            Array containing the times and computed values
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
        """Alias property returning reader values.

        """
        return self.get_data() 
