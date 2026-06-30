"""
Centroid file reader


"""
import logging
import pickle

import numpy as np
import pandas as pd
from pandas.core.groupby import DataFrameGroupBy
from tqdm import tqdm

from pydelling.config import config
from .base_reader import BaseReader

logger = logging.getLogger(__name__)


class StreamlineReader(BaseReader):
    """Read and analyze ParaView streamline CSV outputs.

    Category: reader
    Tags: streamlines, csv, paraview, transport, analysis
    Usage: scripts need arrival times, path lengths, beta values, or material-wise streamline summaries.
    """
    data: pd.DataFrame
    raw_data: pd.DataFrame
    stream_data: DataFrameGroupBy
    is_aperture_zero: bool = False

    def __init__(self, filename, header=False):
        """Initialize the reader for a streamline CSV file.

        Category: reader
        Tags: streamlines, csv, open, reader
        Usage: scripts need streamline records grouped by seed id.

        Returns:
            None: delegates file loading to BaseReader.
        """
        self.header = None
        super().__init__(filename,
                         header=header)

    def read_file(self, opened_file):
        """Read streamline CSV data and normalize coordinate column names.

        Category: reader
        Tags: streamlines, csv, pandas, seedids
        Usage: an opened ParaView streamline CSV should be loaded into grouped pandas data.

        Returns:
            None: populates data, raw_data, and stream_data grouped by SeedIds.
        """
        logger.info(f"Reading streamlines from {self.filename}")
        self.data = pd.read_csv(opened_file)
        self.raw_data = self.data.copy()  # Copy of original data
        self.data = self.data.rename(columns={"Points:0": "x",
                                              "Points:1": "y",
                                              "Points:2": "z",
                                              }
                                     )
        self.data = self.data.apply(pd.to_numeric, args=("coerce",))
        self.stream_data: DataFrameGroupBy = self.data.groupby("SeedIds")

    def compute_arrival_times(self,
                              reason_of_termination: int | None = None,
                              min_x: float | None = None,
                              min_y: float | None = None,
                              ) -> pd.Series:
        """Compute final integration time for each filtered streamline.

        Returns:
            pandas.Series: arrival time per SeedIds group.

        Category: postprocessing
        Tags: streamlines, arrival-time, integration-time, filter
        Usage: scripts need travel-time estimates from streamline endpoints.
        """
        logger.info("Computing arrival times of the streamlines")
        filtered_streamlines = self.filter_streamlines(reason_of_termination=reason_of_termination, min_x=min_x, min_y=min_y)
        temp_series: pd.Series = filtered_streamlines.max()["IntegrationTime"]
        return temp_series

    def compute_arrival_times_per_material(self, reason_of_termination=None) -> pd.Series:
        """Compute streamline arrival times grouped by material and seed id.

        Category: postprocessing
        Tags: streamlines, arrival-time, materials, seedids
        Usage: scripts need travel-time summaries separated by material id.

        Returns:
            pandas.DataFrame: rows with Material ID, SeedIds, and IntegrationTime.
        """
        logger.info("Computing arrival times of the streamlines per material")
        reason_of_termination = reason_of_termination if reason_of_termination else config.streamline_reader.reason_of_termination
        temp_df = self.stream_data
        if reason_of_termination:
            temp_df = temp_df.filter(lambda x: x["ReasonForTermination"].max() == reason_of_termination)

        temp_df['Material ID'] = (temp_df['Material ID'] + 0.45).apply(np.floor)
        temp_series: pd.Series = temp_df.groupby(["Material ID", "SeedIds"]).max()['IntegrationTime']
        temp_series = temp_series.reset_index()

        return temp_series



    def compute_arrival_times_per_material_paula(self, reason_of_termination=None) -> pd.Series:
        """Compute material arrival-time summaries plus cumulative material groups.

        Category: postprocessing
        Tags: streamlines, arrival-time, materials, cumulative, legacy
        Usage: legacy workflows need both per-material rows and grouped IntegrationTime series.

        Returns:
            tuple: material summary DataFrame and cumulative group dictionary.
        """
        logger.info("Computing arrival times of the streamlines per material")
        reason_of_termination = reason_of_termination if reason_of_termination else config.streamline_reader.reason_of_termination
        temp_df = self.stream_data.copy()
        if reason_of_termination:
            temp_df = temp_df.filter(lambda x: x["ReasonForTermination"].max() == reason_of_termination)

        # temp_df['Material ID'] = temp_df['Material ID'].apply(np.ceil)
        temp_df['Material ID'] = (temp_df['Material ID'] + 0.45).apply(np.floor)
        # temp_df['Material ID'] = temp_df['Material ID'].mask(temp_df['Material ID'].between(1, 1.5), 1)
        # temp_df['Material ID'] = temp_df['Material ID'].mask(temp_df['Material ID'].between(1.5, 2.5), 2)
        # temp_df['Material ID'] = temp_df['Material ID'].mask(temp_df['Material ID'].between(2.5, 3.5), 3)
        # temp_df['Material ID'] = temp_df['Material ID'].mask(temp_df['Material ID'].between(3.5, 4.5), 4)
        # temp_df['Material ID'] = temp_df['Material ID'].mask(temp_df['Material ID'].between(4.5, 5), 5)
        temp_series: pd.Series = temp_df.groupby(["Material ID", "SeedIds"]).max()
        temp_series = temp_series.reset_index()

        # AUTOMATIC
        dic = {}
        dic_group = {}
        for group in temp_series.groupby('Material ID').groups:
            ngroup = temp_series.groupby('Material ID').get_group(group)['IntegrationTime']
            dic[group] = ngroup
            dic_group[group] = ''

        b = True
        for key in sorted(dic.keys(), reverse=True):
            if b:
                add = dic[key]
                dic_group[key] = add
                b = False
            else:
                add = pd.concat([add, dic[key]])
                dic_group[key] = add

        return temp_series, dic_group

    def compute_initial_velocities(self,
                                   reason_of_termination: int | None = None,
                                   normalize: bool = True,
                                   index_df: pd.Series=None,
                                   ):
        """Compute initial x-velocity values for each streamline.

        Category: postprocessing
        Tags: streamlines, velocity, initial, normalization
        Usage: arrival-time or transport summaries need weights from starting streamline velocity.

        Returns:
            pandas.Series: initial U:0 values per SeedIds group, optionally normalized.
        """
        logger.info("Computing initial velocities of the streamlines")
        temp_df = self.data
        if index_df is not None:
            seed_ids = index_df["SeedIds"]
            temp_df = temp_df[temp_df["SeedIds"].isin(seed_ids)]
        temp_df = temp_df.groupby("SeedIds").first()
        temp_series = temp_df["U:0"]
        if normalize:
            temp_series /= temp_series.sum()
        temp_series[temp_series < 0.0] = 0.0
        return temp_series

    def compute_length_streamlines(self, reason_of_termination=None) -> pd.Series:
        """Compute final arc length for each filtered streamline.

        Category: postprocessing
        Tags: streamlines, length, arc-length, filter
        Usage: scripts need total path length per streamline.

        Returns:
            pandas.Series: maximum arc_length per SeedIds group.
        """
        logger.info("Computing length of the streamlines")
        reason_of_termination = reason_of_termination if reason_of_termination else config.streamline_reader.reason_of_termination
        temp_df = self.stream_data
        if reason_of_termination:
            temp_df = temp_df.filter(lambda x: x["ReasonForTermination"].max() == reason_of_termination)
        temp_series: pd.Series = temp_df.groupby("SeedIds").max()["arc_length"]
        return temp_series

    def compute_length_streamlines_per_material(self, reason_of_termination=None) -> pd.Series:
        """Compute streamline path-length summaries grouped by material.

        Category: postprocessing
        Tags: streamlines, length, materials, arc-length
        Usage: scripts need material-wise streamline length data.

        Returns:
            pandas.DataFrame: grouped material and seed-id streamline summaries.
        """
        logger.info("Computing length of the streamlines per material")
        reason_of_termination = reason_of_termination if reason_of_termination else config.streamline_reader.reason_of_termination
        temp_df = self.stream_data
        if reason_of_termination:
            temp_df = temp_df.filter(lambda x: x["ReasonForTermination"].max() == reason_of_termination)

        # temp_df['Material ID'] = temp_df['Material ID'].apply(np.ceil)
        temp_df['Material ID'] = (temp_df['Material ID'] + 0.45).apply(np.floor)
        # temp_df['Material ID'] = temp_df['Material ID'].mask(temp_df['Material ID'].between(1, 1.5), 1)
        # temp_df['Material ID'] = temp_df['Material ID'].mask(temp_df['Material ID'].between(1.5, 2.5), 2)
        # temp_df['Material ID'] = temp_df['Material ID'].mask(temp_df['Material ID'].between(2.5, 3.5), 3)
        # temp_df['Material ID'] = temp_df['Material ID'].mask(temp_df['Material ID'].between(3.5, 4.5), 4)
        # temp_df['Material ID'] = temp_df['Material ID'].mask(temp_df['Material ID'].between(4.5, 5), 5)

        temp_series: pd.Series = temp_df.groupby(["Material ID", "SeedIds"]).max()
        temp_series = temp_series.reset_index()

        # AUTOMATIC
        # dic = {}
        # for group in temp_series.groupby('Material ID').groups:
        #     ngroup_series = temp_series.groupby('Material ID').get_group(group)['arc_length']
            # temp_series = temp_series.groupby('Material ID').get_group(group)['arc_length']
            # dic[group] = ngroup

        return temp_series #, dic
        # return ngroup_series

    def compute_beta(self, aperture_field: str = None) -> pd.Series:
        """Compute beta values for streamlines from an aperture field.

        Category: postprocessing
        Tags: streamlines, beta, aperture, integration, transport
        Usage: transport workflows need per-streamline beta calculated along path fragments.

        Returns:
            pandas.Series: maximum beta value per SeedIds group.
        """
        self.number_of_zero_apertures = 0
        aperture_field_file = aperture_field if aperture_field else config.beta_integrator.aperture_field_file if config.beta_integrator.aperture_field_file else None
        assert aperture_field_file, "Define a file containing an aperture field matrix"
        # Read aperture field
        with open(aperture_field_file, "rb") as opened_file:
            aperture_field = pickle.load(opened_file)
        aperture_field = self.fix_aperture_field(aperture_field)
        logger.info(f"Aperture field has been loaded from {aperture_field_file}")
        logger.info("Computing beta values for the streamlines")
        self.data["beta"] = 0.0
        # Filter streamlines
        temp_df = self.filter_streamlines()

        for stream in tqdm(temp_df.groups):
            # if random.random() > 0.01:
            #     continue
            stream_data = self.stream_data.get_group(stream)
            index_group = stream_data.index
            stream_beta_value = self.integrate_beta(stream=stream_data, aperture_field=aperture_field)
            if stream_beta_value == 0.0:
                continue
            if self.is_aperture_zero:
                self.is_aperture_zero = False
                continue
            else:
                self.data.loc[index_group, "beta"] = stream_beta_value

        return self.data.groupby('SeedIds').max()["beta"]

    def integrate_beta(self, stream: pd.DataFrame, aperture_field: np.ndarray):
        """Integrate beta along a single streamline.

        Category: postprocessing
        Tags: streamlines, beta, aperture, integration
        Usage: scripts need the scalar beta contribution for one streamline path.

        Returns:
            float: integrated beta value.
        """
        beta = 0.0
        aperture_field_nx = aperture_field.shape[1]
        aperture_field_ny = aperture_field.shape[0]
        previous_integration_time = 0.0
        previous_aperture = 0.0
        for index, fragment in stream.iterrows():
            # aperture = aperture_from_a_xy_point(x_point=)
            # Nearest neighbour
            index_x = int(np.floor(fragment["x"] / config.beta_integrator.dimension_x * aperture_field_nx))
            index_y = int(np.floor(fragment["y"] / config.beta_integrator.dimension_y * aperture_field_ny))
            index_row = index_y
            index_column = index_x
            if index_row == aperture_field_ny:
                index_row -= 1
            if index_column == aperture_field_nx:
                index_column -= 1

            # Compute tau
            tau = fragment["IntegrationTime"] - previous_integration_time
            previous_integration_time = fragment["IntegrationTime"]
            # if tau < 0.0:
            #     print(tau)

            # Calculate aperture
            aperture = aperture_field[index_row, index_column]
            # if fragment["x"] < 0.001:
            #     print(f"Aperture: {aperture}, x: {fragment['x']} y: {fragment['y']} index_x: {index_x}, index_y: {index_y}")
            if aperture == 0.0:
                aperture = previous_aperture
                continue
            previous_aperture = aperture
            # print(f"Tau: {tau / (365 * 24)} h, Aperture: {aperture} m, Fragment beta: {2 * tau / aperture / (365 * 24 * 3600)}, Cummulated beta: {beta}")
            beta += 2 * tau / aperture / (365 * 24 * 3600)
        # print(f"Stream Finishes")
        # print(f"Computed beta: {beta}")
        return beta

    def get_data(self) -> np.ndarray:
        """Return streamline data as a numpy array.

        Category: reader
        Tags: streamlines, data, numpy, export
        Usage: callers need raw numeric values from the loaded streamline table.

        Returns:
            numpy.ndarray: dataframe values.
        """
        return self.data.values

    def dump_to_csv(self, output_file, delimiter=","):
        """Write the current streamline table to CSV.

        Category: writer
        Tags: streamlines, csv, export, pandas
        Usage: scripts need to persist processed streamline columns.

        Returns:
            None: writes a CSV file.
        """
        print(f"Starting dump into {output_file}")
        # self.data.to_csv(output_file, delimiter=delimiter)
        self.data.to_csv(output_file)
        print(f"The data has been properly exported to the {output_file} file")

    def to_csv(self, output_file, delimiter=","):
        """Write the current streamline table to CSV.

        Category: writer
        Tags: streamlines, csv, export, pandas
        Usage: scripts prefer the to_csv naming convention for exporting processed streamlines.

        Returns:
            None: writes a CSV file.
        """
        print(f"Starting dump into {output_file}")
        # self.data.to_csv(output_file, delimiter=delimiter)
        self.data.to_csv(output_file)
        print(f"The data has been properly exported to the {output_file} file")

    def filter_streamlines(self,
                           reason_of_termination=None,
                           min_x=None,
                           min_y=None,
                           ) -> DataFrameGroupBy:


        """Filter streamlines by termination code and coordinate thresholds.

        Category: postprocessing
        Tags: streamlines, filter, termination, coordinates
        Usage: analyses should include only streamlines that reached a target condition or region.

        Returns:
            pandas.core.groupby.DataFrameGroupBy: filtered data grouped by SeedIds.
        """
        reason_of_termination = reason_of_termination if reason_of_termination else config.streamline_reader.filter.reason_of_termination if config.streamline_reader.filter.reason_of_termination else None
        min_x = min_x if min_x else config.streamline_reader.filter.min_x if config.streamline_reader.filter.min_x else None
        logger.info("Filtering streamlines")
        temp_df = self.data.groupby("SeedIds")
        initial_number_of_streamlines = len(temp_df.groups)
        if reason_of_termination:
            temp_df = temp_df.filter(lambda x: x.max()["ReasonForTermination"] == float(reason_of_termination))
            temp_df = temp_df.groupby("SeedIds")
            logger.info(f"{initial_number_of_streamlines - len(temp_df.groups)} streamlines have been filtered due to 'Reason of termination' filtering (Keeping {len(temp_df.groups) / initial_number_of_streamlines * 100: 2.1f}% of total)")
            # initial_number_of_streamlines = temp_df.shape[0]
        if min_x is not None:
            temp_df = temp_df.filter(lambda x: x.max()["x"] > min_x)
            temp_df = temp_df.groupby("SeedIds")
            logger.info(f"{initial_number_of_streamlines - len(temp_df.groups)} streamlines have been filtered due to 'min_x' filtering (Keeping {len(temp_df.groups) / initial_number_of_streamlines * 100:2.1f}% of total)")

        if min_y is not None:
            temp_df = temp_df.filter(lambda x: x.max()["y"] > min_y)
            temp_df = temp_df.groupby("SeedIds")
            logger.info(f"{initial_number_of_streamlines - len(temp_df.groups)} streamlines have been filtered due to 'min_y' filtering (Keeping {len(temp_df.groups) / initial_number_of_streamlines * 100:2.1f}% of total)")
        return temp_df

    @staticmethod
    def fix_aperture_field(aperture_matrix):
        """Patch aperture-field boundary cells from adjacent interior values.

        Category: preprocessing
        Tags: aperture, matrix, boundary, streamlines
        Usage: beta integration needs a usable aperture value at field boundaries.

        Returns:
            numpy.ndarray: aperture matrix with boundary rows and columns replaced.
        """
        aperture_matrix[0, :] = aperture_matrix[1, :]
        aperture_matrix[:, 0] = aperture_matrix[:, 1]
        aperture_matrix[aperture_matrix.shape[0] - 1, :] = aperture_matrix[aperture_matrix.shape[0] - 2, :]
        aperture_matrix[:, aperture_matrix.shape[1] - 1] = aperture_matrix[:, aperture_matrix.shape[1] - 2]
        return aperture_matrix

    def integrate_variable_within_materials(self, variable,
                                            material_names=None,
                                            add_variable_name_to_output=True,
                                            output_variable_name = None,
                                            *args,
                                            **kwargs
                                            ):
        """Integrate one cumulative variable within materials for every streamline.

        Category: postprocessing
        Tags: streamlines, materials, integration, variables
        Usage: scripts need material-wise totals such as time or length per streamline.

        Returns:
            pandas.DataFrame: integrated variable values by streamline and material.
        """
        logger.info(f'Integrating variable {variable} within the materials for all the streamlines')
        output_list = []
        for streamline in self.stream_data:
            output_list.append(self._integrate_variable_within_materials_single(streamline=streamline[1],
                                                           variable=variable,
                                                           *args,
                                                           **kwargs)
                             )
        output_df = pd.DataFrame(output_list)
        if material_names:
            if add_variable_name_to_output:
                if not output_variable_name:
                    output_variable_name = variable
                output_column_names = [f"{material_names[column]}-{output_variable_name}" for column in output_df.columns]
            else:
                output_column_names = [material_names[column] for column in output_df.columns]
            output_df.columns = output_column_names
        return output_df


    @staticmethod
    def _integrate_variable_within_materials_single(streamline: pd.DataFrame,
                                            variable: str,
                                            categorize_materials: bool=True,
                                            material_id_column: str='Material ID',
                                            material_id_offset: float = 0.45,
                                            ) -> dict:
        """Integrate a cumulative variable by material for one streamline.

        Returns:
            dict: material ids mapped to integrated variable increments.

        Category: postprocessing
        Tags: streamlines, materials, integration, variable
        Usage: material-wise integration is needed for a single streamline group.
        """
        streamline = streamline.reset_index()
        if categorize_materials:
            streamline[material_id_column] = (streamline[material_id_column] + material_id_offset).apply(np.floor)
        material_groups = streamline.groupby(material_id_column).groups
        output_dict = {material: 0.0 for material in material_groups.keys()}
        var_current = None
        for idx, segment in streamline.iterrows():
            if idx == 0:
                # Initial segment
                output_dict[segment[material_id_column]] += segment[variable]
                var_current = segment[variable]
                continue
            if var_current == None:
                raise ValueError('There was an error when processing the initial segment')
            output_dict[segment[material_id_column]] += segment[variable] - var_current
            var_current = segment[variable]
        return output_dict
