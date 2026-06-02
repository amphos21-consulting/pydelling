"""
Base interface for a reader class


"""
import logging

import numpy as np

from pydelling.readers import BaseReader

logger = logging.getLogger(__name__)
from pydelling.config import config
import logging
from pathlib import Path
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
logger = logging.getLogger(__name__)


class PflotranObservationPointReader(BaseReader):
    observation_point: np.ndarray
    observation_boundary: str
    observation_node: int
    variables: dict
    def __init__(self, filename=None):
        """
        __init__ method.
        
        Args:
            filename (Any): Description.
        """
        self.filename = Path(filename) if filename else Path(config.pflotran_reader.filename)
        logger.info(f"Reading PFLOTRAN observation point results file from {self.filename}")
        self.variables = {}
        super().__init__(filename=self.filename)
        self.results = self.data.copy()

        # self.results = {}
        # for time in self.time_keys:
        #     self.results[time] = PflotranResults(time=time, data=self.data[self.time_keys[time]])
        # self.variables = list(self.results[self.time_values[0]].variable_keys)

    def open_file(self, filename):
        """
        open_file method.
        
        Args:
            filename (Any): Description.
        """
        self.data: pd.DataFrame = pd.read_csv(self.filename,
                                              skiprows=1,
                                              header=None,
                                              delim_whitespace=True
                                              )
        header = pd.read_csv(self.filename,
                             nrows=0
                             ).columns.tolist()
        self.data.columns = header

        # Rename time column
        time_column: str = self.data.columns.to_list()[0]
        def limpiar_nombre_variable_mejorado(nombre):
            import re
            # Usaremos una expresión regular para extraer la parte relevante del nombre de la variable
            # Buscamos hasta el primer dígito, paréntesis abierto o corchete cerrado ']'
            match = re.match(r"([a-zA-Z\s]+)\s*\[.*\]", nombre)
            if match:
                return match.group(1).strip()
            else:
                return nombre.strip()

        for col in self.data.columns:
            new_col = limpiar_nombre_variable_mejorado(col)
            self.variables[new_col] = col
            self.data.rename(columns={col: new_col}, inplace=True)
        # Set time column as index and change name to time
        print(self.data.columns)
        self.data.set_index('"Time [y]"', inplace=True)
        self.data.index.name = 'time'

    @property
    def mineral_names(self):
        temp_keys = [key for key in self.variables if 'VF' in key]
        return temp_keys

    @property
    def total_species_names(self):
        temp_keys = [key for key in self.variables if 'Total' in key]
        return temp_keys

    @property
    def free_species_names(self):
        temp_keys = [key for key in self.variables if 'Free' in key]
        return temp_keys

    def plot_variable(self, variable,
                      delete_previous=True,
                      label=None ) -> plt.Axes:
        """
        plot_variable method.
        
        Args:
            variable (Any): Description.
            delete_previous (Any): Description.
            label (Any): Description.
        """
        logger.info(f'Creating lineplot of {variable}')
        if delete_previous:
            plt.clf()
        lineplot: plt.Axes = plt.plot(self.time_series,
                                self.results[variable])[0]
        lineplot.set_label(f'{variable if label is None else label}')
        return lineplot

    def to_csv(self, filename='postprocess/results.csv', variables=None) -> pd.DataFrame:
        """
        to_csv method.
        
        Args:
            filename (Any): Description.
            variables (Any): Description.
        """
        self.create_postprocess_dict()
        logger.info(f'Exporting results to csv')
        if variables:
            plot_results: pd.DataFrame = self.results[variables]
            plot_results.to_csv(filename)
        else:
            self.results.to_csv(filename, index=False)

        # print(self.variables)

    def get_mineral_vf_key(self, mineral) -> str:
        """
        Returns the correct key of the mineral volume fraction name
        Args:
            mineral: mineral name

        Returns:
            mineral volume fraction key
        """
        return f"{mineral}_VF [m^3 mnrl_m^3 bulk]"

    def get_mineral_rate_key(self, mineral) -> str:
        """
        Returns the correct key of the mineral rate name
        Args:
            mineral: mineral name

        Returns:
            mineral rate key
        """
        return f"{mineral}_Rate [mol_m^3_sec]"

    def get_mineral_si_key(self, mineral) -> str:
        """
        Returns the correct key of the mineral si name
        Args:
            mineral: mineral name

        Returns:
            mineral si key
        """
        return f"{mineral}_SI"

    def get_primary_species_key(self, species) -> str:
        """
        Returns the correct key of the given species name
        Args:
            species: specie name

        Returns:
            specie key
        """
        return f"Total_{species}"

    @property
    def time_series(self):
        return self.results.iloc[:, 0]

    @property
    def columns(self):
        return self.results.columns

