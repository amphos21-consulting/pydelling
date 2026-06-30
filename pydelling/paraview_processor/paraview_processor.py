"""
This class provides the framework to read data from a VTK file and do different postprocessing steps


"""

import logging
from typing import Dict

import pandas as pd

from pydelling.paraview_processor.filters import append_arc_length_filter, base_filter, calculator_filter, cell_data_to_point_data_filter, clip_filter, csv_reader_filter, integrate_variable_filter, plot_over_line_filter, save_data_filter, stream_tracer_with_custom_source_filter, table_to_points_filter, vtk_filter, xdmf_filter

logger = logging.getLogger(__name__)
try:
    from paraview.simple import *
    from paraview.vtk.numpy_interface import dataset_adapter as dsa
    from paraview import servermanager as sm
except:
    logger.warning("Paraview python implementation is not properly set-up")

class ParaviewProcessor:
    """Build and inspect ParaView processing pipelines from Python.

    Category: postprocessing
    Tags: paraview, pipeline, vtk, xdmf, filters
    Usage: scripts need to load simulation outputs and compose ParaView filters programmatically.
    """
    current_array: None
   # calculator: Calculator
    pipeline: Dict[str, base_filter] = {}
    vtk_data_counter: int = 0
    xdmf_data_counter: int = 0
    csv_data_counter: int = 0

    def add_vtk_file(self, path, name=None) -> vtk_filter:
        """Add a VTK file reader to the pipeline.

        Category: postprocessing
        Tags: paraview, vtk, reader, pipeline
        Usage: scripts need a LegacyVTKReader-backed data source in the processor pipeline.

        Returns:
            vtk_filter: pipeline wrapper for the VTK reader.
        """
        pipeline_name = name if name else f"vtk_data_{vtk_filter.counter}"
        self.vtk_data_counter += 1
        vtk_filter = vtk_filter(filename=str(path), name=pipeline_name)
        self.pipeline[pipeline_name] = vtk_filter
        logger.info(f"Added VTK file {path} as {vtk_filter.name} object to Paraview processor")
        return vtk_filter

    def add_csv_file(self, path, name=None, coordinate_labels=("x", "y", "z")) -> csv_reader_filter:
        """Add a CSV reader and point conversion source to the pipeline.

        Category: postprocessing
        Tags: paraview, csv, points, reader, pipeline
        Usage: scripts need tabular x/y/z point data available as a ParaView source.

        Returns:
            csv_reader_filter: pipeline wrapper for the CSV point source.
        """
        pipeline_name = name if name else f"vtk_data_{vtk_filter.counter}"
        self.csv_data_counter += 1
        csv_reader = csv_reader_filter(filename=str(path), name=pipeline_name, coordinate_labels=coordinate_labels)
        self.pipeline[pipeline_name] = csv_reader
        logger.info(f"Added CSV file {path} as {csv_reader.name} object to Paraview processor")
        return csv_reader

    def add_xdmf_file(self, path, name=None) -> xdmf_filter:
        """Add an XDMF file reader to the pipeline.

        Category: postprocessing
        Tags: paraview, xdmf, reader, pipeline
        Usage: scripts need an XDMF simulation output source in ParaView.

        Returns:
            xdmf_filter: pipeline wrapper for the XDMF reader.
        """
        pipeline_name = name if name else f"xdmf_data_{xdmf_filter.counter}"
        self.vtk_data_counter += 1
        pv_filter = xdmf_filter(filename=str(path), name=pipeline_name)
        self.pipeline[pipeline_name] = pv_filter
        logger.info(f"Added XDMF file {path} as {pv_filter.name} object to Paraview processor")
        return pv_filter

    def add_calculator(self, input_filter, function='', name=None, output_array_name='Results', *args, **kwargs) -> calculator_filter:
        """Add a Calculator filter to an existing pipeline source.

        Category: postprocessing
        Tags: paraview, calculator, filter, derived-array
        Usage: scripts need to compute a derived ParaView array from an expression.

        Returns:
            calculator_filter: pipeline wrapper for the Calculator filter.
        """
        pipeline_name = name if name else f"calculator_{calculator_filter.counter}"
        calculator_filter = calculator_filter(input_filter=self.process_input_filter(filter=input_filter),
                                           function=function,
                                           name=pipeline_name,
                                           output_array_name=output_array_name, *args, **kwargs)
        self.pipeline[pipeline_name] = calculator_filter
        logger.info(f"Added calculator filter based on {self.get_input_object_name(input_filter)} as {calculator_filter.name} object to Paraview processor")
        return calculator_filter

    def add_cell_data_to_point_data(self, input_filter, name=None) -> cell_data_to_point_data_filter:
        """Add a CellDataToPointData filter to an existing source.

        Category: postprocessing
        Tags: paraview, cell-data, point-data, filter
        Usage: scripts need cell-centered arrays interpolated to mesh points.

        Returns:
            cell_data_to_point_data_filter: pipeline wrapper for the conversion filter.
        """
        pipeline_name = name if name else f"cell_data_to_point_data{cell_data_to_point_data_filter.counter}"
        pv_filter = cell_data_to_point_data_filter(input_filter=self.process_input_filter(filter=input_filter),
                                           name=pipeline_name,
                                                      )
        self.pipeline[pipeline_name] = pv_filter
        logger.info(f"Added cell_data_to_point_data filter based on {self.get_input_object_name(input_filter)} as {pv_filter.name} object to Paraview processor")
        return pv_filter

    def add_clip(self, input_filter, name=None, *args, **kwargs) -> clip_filter:
        """Add a Clip filter to an existing source.

        Category: postprocessing
        Tags: paraview, clip, filter, geometry
        Usage: scripts need to spatially clip simulation output before analysis or export.

        Returns:
            clip_filter: pipeline wrapper for the Clip filter.
        """
        pipeline_name = name if name else f"clip_{clip_filter.counter}"
        pv_filter = clip_filter(input_filter=self.process_input_filter(filter=input_filter),
                                           name=pipeline_name, *args, **kwargs
                              )
        self.pipeline[pipeline_name] = pv_filter
        logger.info(f"Added clip filter based on {self.get_input_object_name(input_filter)} as {pv_filter.name} object to Paraview processor")
        return pv_filter

    def add_table_to_points(self, path, name=None) -> table_to_points_filter:
        """Add a TableToPoints source from a tabular file.

        Category: postprocessing
        Tags: paraview, table-to-points, csv, points
        Usage: scripts need coordinates from a table converted into a ParaView point set.

        Returns:
            table_to_points_filter: pipeline wrapper for the TableToPoints output.
        """
        pipeline_name = name if name else f"table_to_points_{table_to_points_filter.counter}"
        pv_filter = table_to_points_filter(filename=str(path), name=pipeline_name)
        self.pipeline[pipeline_name] = pv_filter
        logger.info(f"Added table to points filter based on {path} as {pv_filter.name} object to Paraview processor")
        return pv_filter


    def add_stream_tracer_with_custom_source(self, input_filter, seed_source, name=None) -> stream_tracer_with_custom_source_filter:
        """Add a StreamTracerWithCustomSource filter.

        Category: postprocessing
        Tags: paraview, streamlines, tracer, seed-source
        Usage: scripts need streamlines from a velocity field using custom seed points.

        Returns:
            stream_tracer_with_custom_source_filter: pipeline wrapper for the stream tracer.
        """
        pipeline_name = name if name else f"stream_tracer_with_custom_source_{stream_tracer_with_custom_source_filter.counter}"
        pv_filter = stream_tracer_with_custom_source_filter(input_filter=self.process_input_filter(filter=input_filter),
                                           seed_source=self.process_input_filter(filter=seed_source),
                                           name=pipeline_name,
                                                        )
        self.pipeline[pipeline_name] = pv_filter
        logger.info(f"Added stream tracer filter based on {self.get_input_object_name(input_filter)} as {pv_filter.name} object to Paraview processor")
        return pv_filter

    def add_append_arc_length(self, input_filter, name=None) -> append_arc_length_filter:
        """Add an AppendArcLength filter to streamline output.

        Category: postprocessing
        Tags: paraview, streamlines, arc-length, filter
        Usage: scripts need cumulative distance along streamline polylines.

        Returns:
            append_arc_length_filter: pipeline wrapper for the arc-length filter.
        """
        pipeline_name = name if name else f"append_arc_length_{append_arc_length_filter.counter}"
        pv_filter = append_arc_length_filter(input_filter=self.process_input_filter(filter=input_filter),
                                           name=pipeline_name
                              )
        self.pipeline[pipeline_name] = pv_filter
        logger.info(f"Added append arc length filter based on {self.get_input_object_name(input_filter)} as {pv_filter.name} object to Paraview processor")
        return pv_filter

    def add_save_data(self, path, proxy, PointDataArrays, CellDataArrays, name=None) -> save_data_filter:
        """Add a SaveData operation for a pipeline object.

        Category: writer
        Tags: paraview, save-data, csv, export
        Usage: scripts need to export selected point and cell arrays from a ParaView proxy.

        Returns:
            save_data_filter: pipeline wrapper for the save operation.
        """
        pipeline_name = name if name else f"save_data_{save_data_filter.counter}"
        pv_filter = save_data_filter(filename=str(path), proxy=self.process_input_filter(filter=proxy),
                                   point_data_arrays=PointDataArrays, cell_data_arrays=CellDataArrays,
                                   name=pipeline_name)
        self.pipeline[pipeline_name] = pv_filter
        logger.info(f"Added csv file based on {self.get_input_object_name(proxy)} as {pv_filter.name} object to Paraview processor")
        return pv_filter


    def add_integrate_variables(self, input_filter, name=None, divide_cell_data_by_volume=False) -> integrate_variable_filter:
        """Add an IntegrateVariables filter to an existing source.

        Category: postprocessing
        Tags: paraview, integrate, variables, filter
        Usage: scripts need integrated scalar or vector values over a dataset.

        Returns:
            integrate_variable_filter: pipeline wrapper for the integration filter.
        """
        pipeline_name = name if name else f"integrate_variables_{integrate_variable_filter.counter}"
        integrate_variables_filter = integrate_variable_filter(input_filter=self.process_input_filter(filter=input_filter),
                                                              name=pipeline_name,
                                                              divide_cell_data_by_volume=divide_cell_data_by_volume
                                                              )
        self.pipeline[pipeline_name] = integrate_variables_filter
        logger.info(
            f"Added integrate_variables filter based on {self.get_input_object_name(input_filter)} as {integrate_variables_filter.name} object to Paraview processor")
        return integrate_variables_filter

    def add_plot_over_line(self, input_filter, name=None, point_1=None, point_2=None, line_resolution=None) -> plot_over_line_filter:
        """Add a PlotOverLine filter to sample data along a segment.

        Category: postprocessing
        Tags: paraview, plot-over-line, sampling, filter
        Usage: scripts need values interpolated along a user-defined line.

        Returns:
            plot_over_line_filter: pipeline wrapper for the line sampler.
        """
        pipeline_name = name if name else f"plot_over_line_{plot_over_line_filter.counter}"
        plot_over_line_filter = plot_over_line_filter(input_filter=self.process_input_filter(filter=input_filter),
                                                   name=pipeline_name,
                                                   point_1=point_1,
                                                   point_2=point_2,
                                                   n_line=line_resolution,
                                                   )
        self.pipeline[pipeline_name] = plot_over_line_filter
        logger.info(
            f"Added plot_over_line_filter filter based on {self.get_input_object_name(input_filter)} as {plot_over_line_filter.name} object to Paraview processor")
        return plot_over_line_filter

    # Utility methods
    def plot_over_z_given_xy_point(self, dataset: base_filter, x_point, y_point, line_resolution=None) -> plot_over_line_filter:
        """Create a vertical PlotOverLine sampler at an x,y coordinate.

        Category: postprocessing
        Tags: paraview, vertical-profile, plot-over-line, sampling

        Returns:
            plot_over_line_filter: line sampler spanning dataset z_min to z_max.
        """
        # Compute z_min and z_max values of the dataset
        point_1 = [x_point, y_point, dataset.z_min]
        point_2 = [x_point, y_point, dataset.z_max]
        plot_over_line_filter = plot_over_line_filter(input_filter=self.process_input_filter(filter=dataset),
                                                   name="plot_over_z_given_xy_point",
                                                   point_1=point_1,
                                                   point_2=point_2,
                                                   n_line=line_resolution,
                                                   )
        return plot_over_line_filter

    def aperture_given_xy_point(self, dataset: base_filter, x_point, y_point, variable=None, target_value=1.0, threshold=0.45, line_resolution=100) -> float:
        """Estimate aperture thickness at an x,y coordinate.

        Category: postprocessing
        Tags: paraview, aperture, vertical-profile, sampling
        Usage: scripts need fracture opening thickness inferred from vertical sampled points.

        Returns:
            float: estimated aperture thickness at the coordinate.
        """
        line_interpolation = self.plot_over_z_given_xy_point(x_point=x_point,
                                                             y_point=y_point,
                                                             line_resolution=line_resolution,
                                                             dataset=dataset,
                                                             )
        line_interpolation_point_data = line_interpolation.point_data
        dataset_mesh_points = dataset.mesh_points
        if variable:
            # If a target variable is defined,
            line_interpolation = line_interpolation_point_data[abs(line_interpolation_point_data[variable] - target_value) < threshold]
            z_points: pd.Series = dataset_mesh_points.iloc[line_interpolation.index]["z"]
            if len(z_points) > 0:
                aperture = abs(z_points.max() - z_points.min())
            else:
                aperture = 0.0
            return aperture

        if not variable:
            # Calculate directly the aperture
            z_points: pd.Series = dataset_mesh_points.iloc[line_interpolation_point_data.index]["z"]
            if len(z_points) > 0:
                aperture = abs(z_points.max() - z_points.min())
            else:
                aperture = 0.0
            return aperture




    def print_pipeline(self) -> str:
        """Print and return a text representation of the pipeline.

        Category: util
        Tags: paraview, pipeline, debug, summary
        Usage: scripts or users need to inspect registered pipeline elements.

        Returns:
            str: formatted pipeline summary.
        """
        identation_level: int = 0
        print_string: str = f""
        print_string += "Paraview filters:\n"
        identation_level += 1
        for pipeline_element in self.pipeline:
            # if type(self.pipeline[pipeline_element]) == dict:
            #     print_string = self.print_pipeline_block(pipeline_dict=self.pipeline[pipeline_element],
            #                               starting_identation_level=identation_level+1,
            #                               output_string=print_string)
            #     continue
            identation = "\t"*identation_level
            print_string += f"{identation}- {pipeline_element} [{self.pipeline[pipeline_element].filter_type}]\n"
        print(print_string)
        return print_string

    def print_pipeline_block(self, pipeline_dict: Dict, output_string:str,  starting_identation_level: int = 0) -> str:
        """Append nested pipeline entries to a text summary.

        Category: util
        Tags: paraview, pipeline, debug, recursion
        Usage: pipeline summaries need to include nested dictionary blocks.

        Returns:
            str: output string with nested pipeline entries appended.
        """
        for pipeline_element in pipeline_dict:
            if type(pipeline_dict[pipeline_element]) == dict:
                output_string = self.print_pipeline_block(pipeline_dict=pipeline_dict[pipeline_element],
                                          starting_identation_level=starting_identation_level+1,
                                          output_string=output_string)
                continue
            identation = "\t"*starting_identation_level
            output_string += f"{identation}- {pipeline_element}\n"
        return output_string

    def get_object(self, name) -> object:
        """Return a pipeline wrapper by name.

        Category: util
        Tags: paraview, pipeline, lookup, filter

        Returns:
            object: registered pipeline object.
        """
        return self.pipeline[name]

    def process_input_filter(self, filter) -> object:
        """Resolve a filter wrapper or pipeline name to the ParaView filter object.

        Category: util
        Tags: paraview, pipeline, filter, proxy

        Returns:
            object: underlying ParaView proxy/filter object.
        """
        if type(filter) == str:
            # Assume the filter specifies the name of the pipeline
            return self.pipeline[filter].filter
        else:
            return filter.filter

    @staticmethod
    def get_input_object_name(filter) -> str:
        """Return the name for a filter wrapper or pipeline reference.

        Category: util
        Tags: paraview, pipeline, name, filter

        Returns:
            str: filter name or pipeline key.
        """
        if type(filter) == str:
            return filter
        else:
            return filter.name




    def __repr__(self):
        return self.print_pipeline()
