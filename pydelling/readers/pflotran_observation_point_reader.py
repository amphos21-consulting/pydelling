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
    """Read and plot PFLOTRAN observation-point time series outputs.

    Category: reader
    Tags: pflotran, observation-points, time-series, geochemistry, plotting
    Use when: scripts need tabular PFLOTRAN observation results, species keys, or quick plots.
    """
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
        """Load the PFLOTRAN observation-point file into a DataFrame.

        Category: reader
        Tags: pflotran, observation-points, csv, dataframe, variables
        Use when: scripts need parsed observation output with normalized variable names.

        Returns:
            None: populates data and variables mappings.
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
        """Return mineral volume-fraction variable names.

        Category: reader
        Tags: pflotran, minerals, volume-fraction, variables
        Use when: scripts need to select mineral VF columns from observation results.

        Returns:
            list: variable names containing VF.
        """
        temp_keys = [key for key in self.variables if 'VF' in key]
        return temp_keys

    @property
    def total_species_names(self):
        """Return total species variable names.

        Category: reader
        Tags: pflotran, species, total, variables
        Use when: scripts need total concentration/species columns from observation results.

        Returns:
            list: variable names containing Total.
        """
        temp_keys = [key for key in self.variables if 'Total' in key]
        return temp_keys

    @property
    def free_species_names(self):
        """Return free species variable names.

        Category: reader
        Tags: pflotran, species, free, variables
        Use when: scripts need free species columns from observation results.

        Returns:
            list: variable names containing Free.
        """
        temp_keys = [key for key in self.variables if 'Free' in key]
        return temp_keys

    def plot_variable(self, variable,
                      delete_previous=True,
                      label=None ) -> plt.Axes:
        """Plot one observation variable against time.

        Category: reader
        Tags: pflotran, observation-points, plot, time-series
        Use when: scripts need a quick matplotlib line for one PFLOTRAN observation variable.

        Returns:
            matplotlib.axes.Axes: plotted line object.
        """
        logger.info(f'Creating lineplot of {variable}')
        if delete_previous:
            plt.clf()
        lineplot: plt.Axes = plt.plot(self.time_series,
                                self.results[variable])[0]
        lineplot.set_label(f'{variable if label is None else label}')
        return lineplot

    def to_csv(self, filename='postprocess/results.csv', variables=None) -> pd.DataFrame:
        """Export observation results to CSV.

        Category: writer
        Tags: pflotran, observation-points, csv, export
        Use when: scripts need selected or full observation results as a CSV artifact.

        Returns:
            None: writes the CSV file.
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
        """Build the PFLOTRAN mineral volume-fraction key.

        Returns:
            str: mineral volume-fraction column key.

        Category: reader
        Tags: pflotran, minerals, volume-fraction, key
        Use when: scripts need to construct the raw mineral VF column name.
        """
        return f"{mineral}_VF [m^3 mnrl_m^3 bulk]"

    def get_mineral_rate_key(self, mineral) -> str:
        """Build the PFLOTRAN mineral rate key.

        Returns:
            str: mineral rate column key.

        Category: reader
        Tags: pflotran, minerals, rate, key
        Use when: scripts need to construct the raw mineral rate column name.
        """
        return f"{mineral}_Rate [mol_m^3_sec]"

    def get_mineral_si_key(self, mineral) -> str:
        """Build the PFLOTRAN mineral saturation-index key.

        Returns:
            str: mineral saturation-index column key.

        Category: reader
        Tags: pflotran, minerals, saturation-index, key
        Use when: scripts need to construct the mineral SI column name.
        """
        return f"{mineral}_SI"

    def get_primary_species_key(self, species) -> str:
        """Build the PFLOTRAN primary species total key.

        Returns:
            str: total species column key.

        Category: reader
        Tags: pflotran, species, primary, key
        Use when: scripts need to construct the Total_species column name.
        """
        return f"Total_{species}"

    @property
    def time_series(self):
        """Return the first result column as the time series.

        Category: reader
        Tags: pflotran, time-series, observation-points
        Use when: plotting routines need x-axis time values from observation results.

        Returns:
            pandas.Series: time values.
        """
        return self.results.iloc[:, 0]

    @property
    def columns(self):
        """Return observation result column labels.

        Category: reader
        Tags: pflotran, observation-points, columns, variables
        Use when: scripts need to inspect available result variables.

        Returns:
            pandas.Index: result column labels.
        """
        return self.results.columns
