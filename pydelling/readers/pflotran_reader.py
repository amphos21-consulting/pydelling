
"""
Base interface for a reader class


"""
import logging

import numpy as np
import pandas

from pydelling.readers import BaseReader

logger = logging.getLogger(__name__)
from pydelling.config import config
import logging
from pathlib import Path
import h5py
import natsort
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from collections import OrderedDict
from tqdm import tqdm
from pydelling.readers import PflotranProcessingUtils
import colorsys
import seaborn as sns



logger = logging.getLogger(__name__)

class PflotranReader(BaseReader, PflotranProcessingUtils):
    """Read and postprocess PFLOTRAN HDF5 result files.

    Category: reader
    Tags: pflotran, hdf5, results, geochemistry, plotting
    Usage: scripts need time-indexed PFLOTRAN variables, observation extraction, or built-in plot helpers.
    """
    def __init__(self,
                 filename=None,
                 variables=None,
                 ) -> None:
        """
        Initialize PflotranReader with HDF5 results file.
        
        Args:
            filename (str or Path): Path to the PFLOTRAN HDF5 output file. If None, uses default from config.
            variables (list, optional): List of variable names to read from the file. If None, reads all available variables.
        
        Returns:
            None
        """
        self.filename = Path(filename) if filename else Path(config.pflotran_reader.filename)
        logger.info(f"Reading PFLOTRAN results file from {self.filename}")
        super().__init__(filename=self.filename)
        self.results = {}
        if variables:
            self.variables = variables
        else:
            self.variables = list(self.data[self.time_keys[self.time_values[0]]])
        if 'Material_ID' not in self.variables:
            self.variables.append('Material_ID')

        for time in tqdm(self.time_keys, desc='Reading PFLOTRAN results'):
            data_slice = self.data[self.time_keys[time]]
            data_slice = {key: data_slice[key] for key in self.variables}
            self.results[time] = PflotranResults(time=time, data=data_slice)
        self.variables = list(self.results[self.time_values[0]].variable_keys)

    def open_file(self, filename) -> None:
        """Open and index a PFLOTRAN HDF5 results file.

        Category: reader
        Tags: pflotran, hdf5, time-series, results
        Usage: scripts need time-step keys and raw HDF5 data available for result extraction.

        Returns:
            None: sets data, time_dict_keys, and time_keys.
        """
        self.data: h5py.File = h5py.File(self.filename, 'r')
        # Obtain time keys
        self.time_dict_keys = natsort.natsorted(OrderedDict({float(key.split(' ')[2]): key for key in self.data.keys() if 'Time' in key}))
        self.time_keys = OrderedDict({float(key.split(' ')[2]): key for key in self.data.keys() if 'Time' in key})
        self.time_keys = {key: self.time_keys[key] for key in self.time_dict_keys}

    @property
    def time_values(self) -> list[float]:
        """Return sorted PFLOTRAN output time values.

        Category: reader
        Tags: pflotran, time-series, hdf5, metadata
        Usage: scripts need available output times for lookup or plotting.

        Returns:
            list: sorted time values.
        """
        return natsort.natsorted(self.time_keys.keys())

    @property
    def coordinates(self) -> dict[str, np.ndarray]:
        """Return PFLOTRAN coordinate arrays.

        Category: reader
        Tags: pflotran, coordinates, hdf5, mesh
        Usage: scripts need x, y, and z coordinate arrays from the results file.

        Returns:
            dict: coordinate arrays keyed by x[m], y[m], and z[m].
        """
        temp_coordinates = self.data['Coordinates']
        temp_df = {'x[m]': np.array(temp_coordinates['X [m]']),
                    'y[m]': np.array(temp_coordinates['Y [m]']),
                    'z[m]': np.array(temp_coordinates['Z [m]']),
                  }
        return temp_df

    def get_data(self) -> np.ndarray:
        """Return a placeholder array for BaseReader compatibility.

        Category: reader
        Tags: pflotran, data, compatibility
        Usage: generic reader code expects get_data but PFLOTRAN results are accessed by time and variable.

        Returns:
            numpy.ndarray: placeholder zero array.
        """
        return np.array(0)

    def build_info(self):
        """Initialize reader metadata storage.

        Category: reader
        Tags: pflotran, metadata, info
        Usage: generic reader code expects an info dictionary.

        Returns:
            None: sets info to an empty dictionary.
        """
        self.info = {}

    def get_observation_point(self, variable, point=(0, 0, 0)) -> pd.DataFrame:
        """Extract one variable's time evolution at a mesh point.

        Returns:
            pandas.DataFrame: variable values through all output times.

        Category: reader
        Tags: pflotran, observation-point, time-series, variable
        Usage: scripts need a temporal series at one i,j,k mesh index.
        """
        temp_array = []
        for time in self.time_values:
            temp_array.append(self.results[time].results[variable][point[0], point[1], point[2]])
        pd_array = pd.DataFrame(np.array(temp_array), columns=[variable])
        return pd_array

    @property
    def mineral_names(self) -> list:
        """Return mineral names inferred from volume-fraction variables.

        Category: reader
        Tags: pflotran, minerals, variables, metadata
        Usage: plotting or analysis needs mineral labels from PFLOTRAN outputs.

        Returns:
            list: mineral names.
        """
        temp_keys = [key.split('_')[0] for key in self.variables if 'VF' in key]
        return temp_keys

    @property
    def species_names(self) -> list:
        """Return species names inferred from Total variables.

        Category: reader
        Tags: pflotran, species, variables, metadata
        Usage: plotting or analysis needs primary species labels from PFLOTRAN outputs.

        Returns:
            list: species names.
        """
        temp_keys = [key.split('_')[1] for key in self.variables if 'Total' in key]
        return temp_keys


    def get_variable_by_time_index(self, variable: str, time_index: int) -> np.ndarray:
        """Return one variable array by output time index.

        Returns:
            numpy.ndarray: variable values at the selected time index.

        Category: reader
        Tags: pflotran, variable, time-index, hdf5
        Usage: scripts need a PFLOTRAN variable using positional time selection.
        """
        return self.results[self.time_values[time_index]].results[variable]

    def get_variable_by_time(self, variable: str, time: float) -> np.ndarray:
        """Return one variable array by exact output time.

        Returns:
            numpy.ndarray: variable values at the selected time.

        Category: reader
        Tags: pflotran, variable, time, hdf5
        Usage: scripts need a PFLOTRAN variable using an explicit time value.
        """
        return self.results[time].results[variable]

    def get_results_by_time(self, time: float) -> dict:
        """Return all result variables for an exact output time.

        Returns:
            dict: variables mapped to arrays for the selected time.

        Category: reader
        Tags: pflotran, results, time, hdf5
        Usage: scripts need the full result snapshot for one time.
        """
        return self.results[time].results

    def get_results_by_time_index(self, time_index: int) -> dict:
        """Return all result variables for a positional output time index.

        Returns:
            dict: variables mapped to arrays for the selected time index.

        Category: reader
        Tags: pflotran, results, time-index, hdf5
        Usage: scripts need the full result snapshot by index.
        """
        return self.results[self.time_values[time_index]].results


    def get_mineral_vf_key(self, mineral) -> str:
        """Build the PFLOTRAN mineral volume-fraction key.

        Returns:
            str: mineral volume-fraction variable key.

        Category: reader
        Tags: pflotran, minerals, volume-fraction, key
        Usage: scripts need to construct a mineral VF variable name.
        """
        return f"{mineral}_VF [m^3 mnrl_m^3 bulk]"

    def get_mineral_rate_key(self, mineral) -> str:
        """Build the PFLOTRAN mineral rate key.

        Returns:
            str: mineral rate variable key.

        Category: reader
        Tags: pflotran, minerals, rate, key
        Usage: scripts need to construct a mineral rate variable name.
        """
        return f"{mineral}_Rate [mol_m^3_sec]"

    def get_mineral_si_key(self, mineral) -> str:
        """Build the PFLOTRAN mineral saturation-index key.

        Returns:
            str: mineral saturation-index variable key.

        Category: reader
        Tags: pflotran, minerals, saturation-index, key
        Usage: scripts need to construct a mineral SI variable name.
        """
        return f"{mineral}_SI"

    def get_primary_species_key(self, species) -> str:
        """Build the PFLOTRAN primary species total key.

        Returns:
            str: Total_species variable key.

        Category: reader
        Tags: pflotran, species, primary, key
        Usage: scripts need to construct a primary species total variable name.
        """
        return f"Total_{species}"

    def plot_primary_species(self, type='1D', postprocess_dir='./postprocess') -> None:
        """Plot primary species evolution along a 1D domain.

        Category: reader
        Tags: pflotran, species, plot, time-series, 1d
        Usage: scripts need PNG plots of Total_species values over space and time.

        Returns:
            None: saves individual species plots.
        """
        logger.info(f'Plotting [{self.species_names}] primary species from {self.filename}')
        postprocess_dir = Path(postprocess_dir)
        if type == '1D':
            for species in self.species_names:
                # Generate rate plots
                primary_species_key = self.get_primary_species_key (species)
                plot_df = pd.DataFrame()
                plt.clf()
                for time in config.postprocessing.times:
                    specie_data = self.results[time].results[primary_species_key][:, 0, 0]
                    specie_data_pd = pd.DataFrame (specie_data, columns=[f'{time} years'])
                    plot_df = plot_df.combine_first (specie_data_pd)
                plot_df = plot_df.combine_first (self.x_centroid)
                plot_df = plot_df.set_index ('x[m]')
                plot_df = plot_df.reindex(natsort.natsorted(plot_df.columns), axis=1)
                line_plot: plt.Axes = sns.lineplot (data=plot_df)
                line_plot.set_xlabel ('X [m]')
                line_plot.set_ylabel (f'{species}')
                plt.savefig(postprocess_dir / f'{species}.png')

    def plot_vf_variation(self, type='1D', postprocess_dir='./postprocess', ignored_minerals=[]) -> None:
        """Plot mineral volume-fraction variation over time.

        Category: reader
        Tags: pflotran, minerals, volume-fraction, plot, 1d
        Usage: scripts need PNG plots of mineral precipitation or dissolution changes.

        Returns:
            None: saves individual mineral variation plots.
        """
        logger.info(f'Plotting [{self.mineral_names}] primary species from {self.filename}')
        postprocess_dir = Path(postprocess_dir)
        postprocess_dir.mkdir(exist_ok=True)
        if type == '1D':
            for mineral in self.mineral_names:
                if mineral in ignored_minerals:
                    continue
                # Generate porosity variation plots
                primary_minerals_key = self.get_mineral_vf_key(mineral)
                plot_df = pd.DataFrame()
                plt.clf()
                # Save initial mineral volumes and porosity
                assert 'Porosity' in self.results[0.0].results, 'Porosity must be within the PFLOTRAN output variables'
                initial_porosity = self.results[0.0].results['Porosity']
                initial_mineral_vf = self.results[0.0].results[primary_minerals_key][:, 0, 0]
                for time in config.postprocessing.times:
                    mineral_vf = self.results[time].results[primary_minerals_key][:, 0, 0]
                    mineral_variation = mineral_vf - initial_mineral_vf
                    mineral_vf_pd = pd.DataFrame (mineral_variation, columns=[f'{time} years'])
                    plot_df = plot_df.combine_first (mineral_vf_pd)
                plot_df = plot_df.combine_first (self.x_centroid)
                plot_df = plot_df.set_index ('x[m]')
                plot_df = plot_df.reindex(natsort.natsorted(plot_df.columns), axis=1)
                line_plot: plt.Axes = sns.lineplot (data=plot_df)
                line_plot.set_xlabel ('X [m]')
                line_plot.set_ylabel (f'{mineral} volume fraction variation')
                plt.savefig(postprocess_dir / f'{mineral}.png')

    def plot_total_porosity_variation(self, type='1D', postprocess_dir='./postprocess', ignored_minerals=[]) -> None:
        """Plot total porosity variation from mineral volume changes.

        Category: reader
        Tags: pflotran, porosity, minerals, plot, 1d
        Usage: scripts need porosity-change plots derived from mineral volume-fraction changes.

        Returns:
            None: saves a porosity variation plot.
        """
        logger.info(f'Plotting [{self.mineral_names}] primary species from {self.filename}')
        postprocess_dir = Path(postprocess_dir)
        postprocess_dir.mkdir(exist_ok=True)
        plot_df = pd.DataFrame()

        if type == '1D':
            assert 'Porosity' in self.results[0.0].results, 'Porosity must be within the PFLOTRAN output variables'
            initial_porosity = self.results[0.0].results['Porosity'][:, 0, 0]
            for time in config.postprocessing.times:
                total_porosity_variation = np.zeros_like(initial_porosity)
                for mineral in self.mineral_names:
                    if mineral in ignored_minerals:
                        continue
                    # Generate porosity variation plots
                    primary_minerals_key = self.get_mineral_vf_key(mineral)
                    initial_mineral_vf = self.results[0.0].results[primary_minerals_key][:, 0, 0]
                    mineral_vf = self.results[time].results[primary_minerals_key][:, 0, 0]
                    mineral_variation = mineral_vf - initial_mineral_vf
                    total_porosity_variation += mineral_variation

                total_porosity_variation = total_porosity_variation / initial_porosity * 100
                mineral_vf_pd = pd.DataFrame(total_porosity_variation, columns=[f'{time} years'])
                plot_df = plot_df.combine_first(mineral_vf_pd)
            plot_df = plot_df.combine_first(self.x_centroid)
            plot_df = plot_df.set_index('x[m]')
            plot_df = plot_df.reindex(natsort.natsorted(plot_df.columns), axis=1)
            line_plot: plt.Axes = sns.lineplot (data=plot_df)
            line_plot.set_xlabel ('X [m]')
            line_plot.set_ylabel (f'{mineral} volume fraction variation')
        plt.savefig(postprocess_dir / f'{mineral}.png')

    def plot_1D_slice_of_variable(self, variable,
                                  times=None,
                                  axis='x',
                                  coordinate=0,
                                  postprocess_dir='./postprocess',
                                  color='b',
                                  ) -> plt.Axes:
        """Plot a 1D spatial slice of a variable for selected times.

        Category: reader
        Tags: pflotran, slice, plot, variable, 1d
        Usage: scripts need spatial profiles through a 3D variable along one axis.

        Returns:
            matplotlib.axes.Axes: axes containing plotted slice lines.
        """
        fig, ax = plt.subplots()
        ax: plt.Axes
        ax_color = ax._get_lines.get_next_color()
        if times is None:
            times = [self.time_values[0]]
        elif times == 'all':
            times = self.time_values
        else:
            times = times

        for time_id, time in enumerate(times):
            data = self.get_variable_by_time(variable, time)
            data_slice = self.get_slice_from_coordinates(data=data,
                                                         axis=axis,
                                                         coordinate=coordinate
                                                         )
            dims = self.get_shape_dimensions(data_slice)
            n_times = len(times)
            # Convert hex to rgb
            next_color = tuple(int(ax_color.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4))
            original_color = colorsys.rgb_to_hls(*next_color)
            darker_color = colorsys.hls_to_rgb(original_color[0], 0.25 + 0.5 * time_id / n_times, original_color[2])
            data_slice = data_slice.flatten()
            x_data = self.axis_centroids(dims)
            ax.plot(x_data, data_slice, label=f'{time} years', color=darker_color)
            ax.set_xlabel(self.axis_translator[dims])
        ax.set_ylabel(variable)
        ax.grid()
        return ax

    def plot_1D_rigge_variable(self,
                               variable,
                                 times=None,
                                 axis='x',
                                 coordinate=0,
                                 postprocess_dir='./postprocess',
                                 color='b',
                                 ) -> plt.Axes:

        """Create a ridgeline plot of a 1D variable slice over time.

        Category: reader
        Tags: pflotran, ridgeline, plot, variable, time-series
        Usage: scripts need stacked spatial profiles for multiple PFLOTRAN times.

        Returns:
            None: builds a seaborn FacetGrid plot.
        """
        if times is None:
            times = [self.time_values[0]]
        elif times is 'all':
            times = self.time_values
        else:
            times = times

        df = pd.DataFrame()

        for time_id, time in enumerate(times):
            data = self.get_variable_by_time(variable, time)
            data_slice = self.get_slice_from_coordinates(data=data,
                                                         axis=axis,
                                                         coordinate=coordinate
                                                         )
            dims = self.get_shape_dimensions(data_slice)
            n_times = len(times)
            # Convert hex to rgb
            label_name = self.get_shape_dimensions(data_slice)
            data_slice = data_slice.flatten()
            x_data = self.axis_centroids(dims)
            times_var = [time] * len(x_data)
            df = pd.concat([df, pd.DataFrame({'x': x_data, 'y': data_slice, 'times': times_var})])


        a = 2
        sns.set_theme(style="white", rc={"axes.facecolor": (0, 0, 0, 0)})

        # Initialize the FacetGrid object
        pal = sns.cubehelix_palette(len(times), rot=-.25, light=.7)
        g = sns.FacetGrid(df, row="times", hue="times", aspect=15, height=.5, palette=pal)

        g.map(sns.lineplot, "x", 'y',
              clip_on=False,
            alpha=1, linewidth=1.5)
        # Fill the space between the line and the curve
        g.map(plt.fill_between, "x", "y", alpha=.2, clip_on=False)

        # Add a horizontal line to show the maximum value
        max_value = df['y'].max()
        # g.map(plt.axhline, y=max_value, lw=0.5, clip_on=True, color='k')
        def label(x, color, label):
            ax = plt.gca()
            ax.text(-.04, .2, label, fontweight="bold", color=color,
                    ha="left", va="center", transform=ax.transAxes)


        g.map(label, 'x')
        # Set the subplots to overlap
        g.figure.subplots_adjust(hspace=0.5)
        # Change the x axis labels

        # Remove axes details that don't play well with overlap
        g.set_titles("")
        g.set(yticks=[], ylabel="")
        g.despine(bottom=True, left=True)
        g.set_xlabels('x [m]')
        # Set y label in the middle
        g.fig.text(0.01, 0.5, variable, va='center', rotation='vertical')
        # Shrink the plot to fit the legend
        g.fig.subplots_adjust(left=0.1, bottom=0.15)








class PflotranResults:
    """Container for PFLOTRAN variables at one output time.

    Category: PFLOTRAN reader.
    Tags: pflotran, results, time-step, variables.
    Usage: to inspect available result arrays for a single
        PFLOTRAN output time.
    """
    def __init__(self, time, data) -> None:
        """Initialize a PFLOTRAN result snapshot.

        Category: PFLOTRAN reader.
        Tags: pflotran, results, time-step, arrays.
        Usage: wrapping HDF5 datasets from one output time into NumPy arrays.
        Args:
            time (float): Simulation time value for this results snapshot.
            data (dict): Dictionary mapping variable names to their data arrays.
        Side effects:
            Converts each raw dataset into a NumPy array and stores
            ``variable_keys``.
        """
        self.time = time
        self.raw_data = data
        self.results = {key: np.array(self.raw_data[key]) for key in self.raw_data}
        self.variable_keys = self.results.keys()

    def __repr__(self) -> str:
        return f"Results of time {self.time}"

    @property
    def mineral_names(self) -> list[str]:
        """Return mineral names inferred from volume-fraction variables.

        Category: PFLOTRAN reader.
        Tags: pflotran, minerals, volume-fraction, variables.
        Usage: listing mineral variables present in a result snapshot.
        Returns:
            list[str]: Prefixes of variable keys containing ``VF``.
        """
        temp_keys = [key.split('_')[0] for key in self.variable_keys if 'VF' in key]
        return temp_keys

    @property
    def species_names(self) -> list[str]:
        """Return species names inferred from total concentration variables.

        Category: PFLOTRAN reader.
        Tags: pflotran, species, total-concentration, variables.
        Usage: listing primary species variables present in a result snapshot.
        Returns:
            list[str]: Species components of variable keys containing ``Total``.
        """
        temp_keys = [key.split('_')[1] for key in self.variable_keys if 'Total' in key]
        return temp_keys



