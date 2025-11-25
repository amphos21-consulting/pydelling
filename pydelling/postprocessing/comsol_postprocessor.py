import numpy as np
import pandas as pd
import mph
import re
import jpype
from tqdm import tqdm
import logging
from pathlib import Path

from .comsol_results.comsol_plotgroup1D import _PlotGroup1D
from .comsol_results.comsol_plotgroup2D import _PlotGroup2D
from .comsol_results.comsol_table import _Table
from .comsol_results.comsol_derived_values import _DerivedValue

logger = logging.getLogger(__name__)


class ComsolPostprocessor:
    """
    A class to handle postprocessing of COMSOL simulation results.

    Warning: A valid COMSOL installation is required to use this class as well as java 11 or higher. Moreover, the oficial version of python is recommended, since the Microsoft Store version could cause issues with the COMSOL API.

    """

    def __init__(self,
                file_path: str,
                version: str | None = None,
                comp_tag: str = 'comp1',
                geom_tag: str = 'geom1',
                ):
        """
        Initialize the ComsolPostprocessor with the path to the COMSOL file.

        Parameters:
            file_path (str): Path to the COMSOL file.
            version (str or bool): The version of COMSOL to use. If False, the default version is used.
            comp_tag (str): The tag of the component in the COMSOL model. Defaults to 'comp1'.
            geom_tag (str): The tag of the geometry in the specified component. Defaults to 'geom1'.
        """
        self.file_path = file_path
        self.client = mph.start(version=version)
        self.model_standalone = self.client.load(file_path)
        self.model = self.model_standalone.java
        self.comp = self.model.modelNode(comp_tag)
        self.geom = self.comp.geom(geom_tag)
        self.childs = []
        self.export_configuration = None

    def plot_group_1D(self,
                    tag: str | None = None,
                     dataset: str | None = None,
                     label: str | None = None,
                     time: list[float] | str | None = None,
                     xlabel: str | bool | None = None,
                     ylabel: str | bool | None = None,
                     xrange: list | None = None,
                     yrange: list | None = None,
                     xlog: bool | None = None,
                     ylog: bool | None = None,
                     axisprecision: int | None = None,
                     twoyaxes: bool | None = None,
                     yseclabel: str | None = None,
                     ysecrange: list | None = None,
                     yseclog: bool | None = None,
                     legendactive: bool | None = None,
                     legendlayout: str | None = None,                     
                     legendpos: str | None = None,
                     legendcolumncount: int | None = None,
                     ):
        """
        Create a 1D Plot Group for COMSOL postprocessing.
        
        This method creates an instance of the PlotGroup1D class, passing the model
        and all necessary parameters.
        
        Parameters:
            tag (str or None): The tag of the plot group to edit. If None, a new plot group is created. Defaults to None.
            dataset (str or None): The name of the dataset to use for the plot group. If None, the dataset is not set. Defaults to None.
            label (str or None): The title of the plot group. If None, the title is not set. Defaults to None.
            time (list of float or "all" or 'first' or 'last' or None): The time steps to use for the plot group. If "all", all time steps are used. If None, time is not set. Defaults to None.
            xlabel (str or None): The label of the x-axis. If None, the label is not set. Defaults to None.
            ylabel (str or None): The label of the y-axis. If None, the label is not set. Defaults to None.
            xrange (list or None): The range of the x-axis. If None, automatic range is used. Defaults to None.
            yrange (list or None): The range of the y-axis. If None, automatic range is used. Defaults to None.
            xlog (bool): If True, the x-axis is logarithmic. Defaults to False.
            ylog (bool): If True, the y-axis is logarithmic. Defaults to False.
            axisprecision (int): The number of decimal places to use for the axis labels. Defaults to 4.
            twoyaxes (bool): If True, a second y-axis is added to the plot. Defaults to False.
            yseclabel (str or None): The label of the second y-axis. If None, the label is not set. Defaults to None.
            ysecrange (list or None): The range of the second y-axis. If None, automatic range is used. Defaults to None.
            yseclog (bool): If True, the second y-axis is logarithmic. Defaults to False.
            legendactive (bool): If True, the legend is shown. Defaults to True.
            legendpos (str or None): The position of the legend. Valid values are upperright | middleright | lowerright | upperleft | middleleft | lowerleft | middleright | center | middleleft. If None, the position is not set. Defaults to None.        
        Returns:
            A PlotGroup1D object.
        """
        plotgroup = _PlotGroup1D(
            self,
            tag,
            dataset,
            label,
            time,
            xlabel,
            ylabel,
            xrange,
            yrange,
            xlog,
            ylog,
            axisprecision,
            twoyaxes,
            yseclabel,
            ysecrange,
            yseclog,
            legendactive,
            legendlayout,
            legendpos,
            legendcolumncount,
        )
        return plotgroup

    def plot_group_2D(self,
                     tag: str | None = None,
                     dataset: str | None = None,
                     label: str | None = None,
                     time: float | str | None = None,
                     selection: str | list | None = None,
                     view: str | None = None,
                     showlegends: bool | None = None,
                     legendcolor: str | None = None,
                     legendpos: str | None = None,
                     showlegendsmaxmin: bool | None = None,
                     showlegendsunit: bool | None = None,
                     legendformattingactive: bool | None = None,
                     legendnotation: str | None = None,
                     legendprecision: int | None = None,
                     ):
            """
            A class to handle the properties of a COMSOL 2D Plot Group.
            Parameters:
                tag (str or None): The tag of the plot group to edit. If None, a new plot group is created. Defaults to None.
                dataset (str or None): The name of the dataset to use for the plot group. If None, the dataset is not set. Defaults to None.
                label (str or None): The label of the plot group. If None, the label is not set. Defaults to None.
                time (float or None): The time step to use for the plot group. If None, the time is not set. Defaults to None.
                selection (str or list or None): The selection to use for the plot group. If "all", all domains are selected. If a Explicit Selection tag is given, it is used. If a list of integers is given, those domains are selected. If None, the selection is not set. Defaults to None.
                view (str or None): The tag of the view to use for the plot group or 'auto'. If None, the view is not set. Defaults to None.
                showlegends (bool or None): If True, the color legend is shown. If None, the legend setting is not set. Defaults to None.
                legendcolor (str or None): The color of the values of the legend. Valid values are black | blue | cyan | gray | green | magenta | red | white | yellow. If None, legendcolor is not set. Defaults to None.
                legendpos (str or None): The position of the color legend. Valid values are alternating | bottom | left | leftdouble | right | rightdouble. If None, legendpos is not set. Defaults to None.
                showlegendsmaxmin (bool or None): If True, the maximum and minimum values are shown on the legend. If None, showlegendsmaxmin setting is not set. Defaults to None.
                showlegendsunit (bool or None): If True, the unit is shown on the legend. If None, showlegendsunit setting is not set. Defaults to None.
                legendformattingactive (bool or None): If True, the formatting of the legend is active. If None, legendformattingactive setting is not set. Defaults to None.
                legendnotation (str or None): The notation of the legend. Valid values are automatic | scientific | engineering. legendformattingactive must be True for the legendnotation to be set. If None, legendnotation is not set. Defaults to None.
                legendprecision (int or None): The number of decimal places to use for the legend. legendformattingactive must be True for the legendprecision to be set. If None, legendprecision is not set. Defaults to None.
            Returns:
                A PlotGroup2D object.
            """
            plotgroup = _PlotGroup2D(self, tag, dataset, label, time, selection, view, showlegends, legendcolor, legendpos, showlegendsmaxmin, showlegendsunit, legendformattingactive, legendnotation, legendprecision)
            return plotgroup
    
    def table(self,
                tag: list | None = None,
                columnheaders: str | None = None,
                derived_value: None = None
              ):
        """
        A class to handle the properties of a COMSOL Table.
        Parameters:
            tag (str or None): The tag of the table. If None, a new table is created. Defaults to None.
            columnheaders (list of str or None): A list with the headers of the columns. List lenght must be the same as the number of columns. If None, the column headers are not set. Defaults to None.
            derived_value (_DerivedValue or None): The derived value that writes the table. If None, the derived_value is not set. Defaults to None.
        """
        table = _Table(self, tag, columnheaders, derived_value)
        return table
    
    def derived_value(self,
                    tag: str | None = None,
                    dev_type: str | None = None,
                    table_tag: str | None = None,
                    expression: list | None = None,
                    unit: list | None = None,
                    description: list | None = None,
                    dataset: str | None = None,
                    label: str | None = None,
                    time: str | list | None = None,
                    selection: str | list | None = None,
                    method: str | None = None,
                    integration_order: str | int | None = None,
                    consider2Daxi: bool | None = None,
                    normalization: str | None = None,
                    transformation: str | None = None,
                    transform_method: str | None = None,
                    transform_cumulative: bool | None = None,
                    ):
        """
        A class to handle the properties of a COMSOL Derived Value.
        Parameters:
            tag (str or None): The tag of the derived value. If None, dev_type must be provided.
            dev_type (str or None): The type of Derived Value. Valid values are "EvalPoint", "EvalGlobal", "AvLine", "AvSurface", "AvVolume", "IntLine", "IntSurface", "IntVolume", "MinLine", "MinSurface", "MinVolume, "MaxLine", "MaxSurface" and "MaxVolume". If tag is not None, dev_type would be overwriten. If tag is None, dev_type must be provided. Defaults to None.
            table_tag (str or None): The tag of the table to export the results to. If 'new', a new table is created. If None, the table assosciated with this derived value will be used. If its not associated to any table a new one will be created. Defaults to None.
            expression (list or None): A list with the expression to evaluate. If None, the expression is not set. Defaults to None.
            unit (list or None): A list with the unit of the expressions. If None, the unit is not set. Defaults to None.
            description (list or None): A list with the description of the expressions. If None, the description is not set. Defaults to None.
            dataset (str or None): The name of the dataset to use for the Derived Value. If None, the dataset is not set. Defaults to None.
            label (str or None): The label of the Derived Value. If None, the label is not set. Defaults to None.
            time (str or list or None): The time step to use for the Derived Value. Valid values are "all", "first", "last" or a list with floats. If None, the time is not set. Defaults to None.
            selection (str or list or None): The list of elements to evaluate. If "all", all entities are selected. If a Explicit Selection tag is given, it is used. If None, the selection is not set. Defaults to None.
            method (str or None): The integration method for Averages and Integrals. Valids values are "auto", "integration" and "summation". If None, the method is not set. Defaults to None.
            integration_order (str or int or None): The integration order if method is "auto" or "integration". If "auto" the integration order is set automatically. If None, the integration order is not set. Defaults to None.
            consider2Daxi (bool or None): Consider or not the revolution dimension when using Average or Integral. If None, the parameter is not set. Defaults to None (in COMSOL the default parameter is True).
            normalization (str or None): Normalize the results. Valid values are "first", "last", "max", "none". If None, the parameter is not set. Defaults to None. Warning: do not confuse None with "none". Use None to leave the parameter unset in COMSOL, and the string "none" to specify that the results should not be normalized.
            transformation (str or None): Transform the time data series. Valid values are "average", "integral", "minimum", "maximum", "rms", "stddev", "variance" and "none. If None, the parameter is not set. Defaults to None. Warning: do not confuse None with "none". Use None to leave the parameter unset in COMSOL, and the string "none" to specify that the results should not be transformed.
            transform_method: The method to use for data series transformation. Valid values are "auto", "integration" and "summation". If None, the method of the transformation is not set. Defaults to None.
            tranform_cumulative (bool or None): Make the table values as a cumulative integration, when transformation is set to "integral". If None, the properity is not set. Defaults to None.
        """
        derived_value = _DerivedValue(self, tag, dev_type, table_tag, expression, unit, description, dataset, label, time, selection, method, integration_order, consider2Daxi, normalization, transformation, transform_method, transform_cumulative)
        return derived_value

    class _ExportProperties:
        def __init__(self,
                     width: int | None = None,
                     height: int | None = None,
                     resolution: int | None = None,
                     font_size: int | None = None,
                     title: bool | None = None,
                     legend: bool | None = None,
                     axes: bool | None = None,
                     grid: bool | None = None,
                     logo: bool | None = None,
                     ):
            """
            A class to handle the properties of a COMSOL plot export.
            Parameters:
                width (int or None): The width of the plot in pixels. If None, width is not set. Defaults to None.
                height (int or None): The height of the plot in pixels. If None, height is not set. Defaults to None.
                resolution (int or None): The resolution of the plot in dpi. If None, resolution is not set. Defaults to None.
                font_size (int or None): The font size of the plot. If None, font_size is not set. Defaults to None.
                title (bool or None): If True, the title is shown. If None, title setting is not set. Defaults to None.
                legend (bool or None): If True, the legend is shown. If None, legend setting is not set. Defaults to None.
                axes (bool or None): If True, the axes are shown. If None, axes setting is not set. Defaults to None.
                grid (bool or None): If True, the grid is shown. If None, grid setting is not set. Defaults to None.
                logo (bool or None): If True, the COMSOL logo is shown. If None, logo setting is not set. Defaults to None.
            """
            self.width = width
            self.height = height
            self.resolution = resolution
            self.font_size = font_size
            self.title = title
            self.legend = legend
            self.axes = axes
            self.grid = grid
            self.logo = logo
    
    def export_properties(self,
                     width: int | None = None,
                     height: int | None = None,
                     resolution: int | None = None,
                     font_size: int | None = None,
                     title: bool | None = None,
                     legend: bool | None = None,
                     axes: bool | None = None,
                     grid: bool | None = None,
                     logo: bool | None = None,
                     ):
            """
            A class to handle the properties of a COMSOL plot export.
            Parameters:
                width (int or None): The width of the plot in pixels. If None, width is not set. Defaults to None.
                height (int or None): The height of the plot in pixels. If None, height is not set. Defaults to None.
                resolution (int or None): The resolution of the plot in dpi. If None, resolution is not set. Defaults to None.
                font_size (int or None): The font size of the plot. If None, font_size is not set. Defaults to None.
                title (bool or None): If True, the title is shown. If None, title setting is not set. Defaults to None.
                legend (bool or None): If True, the legend is shown. If None, legend setting is not set. Defaults to None.
                axes (bool or None): If True, the axes are shown. If None, axes setting is not set. Defaults to None.
                grid (bool or None): If True, the grid is shown. If None, grid setting is not set. Defaults to None.
                logo (bool or None): If True, the COMSOL logo is shown. If None, logo setting is not set. Defaults to None.
            """
            export_config = self._ExportProperties(width, height, resolution, font_size, title, legend, axes, grid, logo)
            self.export_configuration = export_config
        
    def _export(self, plotgroup_tag: str, export_path: str):
        """
        Export a plot group to a PNG file.
        Parameters:
            plotgroup_tag (str): The tag of the plot group to export.
            export_path (str): The path to save the PNG file.
        Warning:
            If the ComsolPostprocessor.export_properties() is not used, the export properties will be the default ones.
        """
        export_tags = self.model.result().export().tags()
        if 'img1' in export_tags:
            image_export = self.model.result().export().remove('img1')
        image_export = self.model.result().export().create('img1', 'Image')

        image_export.set('plotgroup', plotgroup_tag)        
        logger.info(f"Exporting image {export_path}")
        image_export.set('pngfilename', export_path)
        if self.export_configuration is not None:
            image_export.set('unit', 'px')
            image_export.set('size', 'manualweb')
            if self.export_configuration.width is not None: image_export.set('width', str(int(self.export_configuration.width)))
            if self.export_configuration.height is not None: image_export.set('height', str(int(self.export_configuration.height)))
            if self.export_configuration.resolution is not None: image_export.set('resolution', str(int(self.export_configuration.resolution)))
            if self.export_configuration.font_size is not None: image_export.set('fontsize', str(int(self.export_configuration.font_size)))
            if self.export_configuration.title is not None:
                if self.export_configuration.title: 
                    image_export.set('title1d', 'on')
                    image_export.set('title2d', 'on')
                    image_export.set('title3d', 'on')
                else:
                    image_export.set('title1d', 'off')
                    image_export.set('title2d', 'off')
                    image_export.set('title3d', 'off')
            if self.export_configuration.legend is not None:
                if self.export_configuration.legend:
                    image_export.set('legend1d', 'on')
                    image_export.set('legend2d', 'on')
                    image_export.set('legend3d', 'on')
                else:
                    image_export.set('legend1d', 'off')
                    image_export.set('legend2d', 'off')
                    image_export.set('legend3d', 'off')
            if self.export_configuration.axes is not None:
                if self.export_configuration.axes:
                    image_export.set('axes1d', 'on')
                    image_export.set('axes2d', 'on')
                    image_export.set('axisorientation', 'on')
                else:
                    image_export.set('axes1d', 'off')
                    image_export.set('axes2d', 'off')
                    image_export.set('axisorientation', 'off')
            if self.export_configuration.grid is not None:
                if self.export_configuration.grid:
                    image_export.set('showgrid', 'on')
                    image_export.set('grid', 'on')
                else:
                    image_export.set('showgrid', 'off')
                    image_export.set('grid', 'off')
            if self.export_configuration.logo is not None:
                if self.export_configuration.logo:
                    image_export.set('logo1d', 'on')
                    image_export.set('logo2d', 'on')
                    image_export.set('logo3d', 'on')
                else:
                    image_export.set('logo1d', 'off')
                    image_export.set('logo2d', 'off')
                    image_export.set('logo3d', 'off')
        image_export.run()

    def apply(self):
        """
        Apply the changes of the ComsolPostprocessor to the COMSOL API model.
        """
        for child in self.childs:
            child.apply()

    def get_childs(self):
        """
        Get the tags of the loaded childs of the ComsolPostprocessor
        """
        tags = []
        for child in self.childs:
            tags.append(child.tag)
        return tags

    def run_all_plots(self):
        """
        Run all plot groups in the COMSOL model.
        """
        for child in self.childs:
            child.run()

    def export_all_plots(self):
        """
        Export all plot groups in the COMSOL model to PNG files.
        Warning:
            If the ComsolPostprocessor.export_properties() is not used, the export properties will be the default ones.
        """
        for child in self.childs:
            child.export()

    def get_variable_evolution_at_point(self, 
                                        dataset: str, 
                                        var_list: list, 
                                        point_list: list):
        """
        Get the evolution of specified variables at specified points over time.

        Parameters:
            dataset (str): The tag of the dataset of the solution.
            var_list (list of str): A list with the names of the variables to evaluate.
            point_list (list of list): A list of points' geomertry tags where the variable evolution is to be computed.
            coord_labels (list of str): A list with the names of the coordinates to evaluate. Defaults to ['r', 'z'].
        Returns:
            tuple: **t** (numpy.ndarray) and **var_list** (list of list of lists). (i) A 1D array of unique time steps (in days) from the dataset.
            (ii) A list with a list of lists for each variable where each inner list contains the variable values
            at the corresponding point in `point_list` over time.
        """
        points = [self.geom.feature(name) for name in point_list]

        # Get coordinates of points
        coords_list = []
        for point in points:
            coords = point.getDoubleArray('p')
            coords_list.append(coords)

        datasetname = self.model.result().dataset(dataset).name()
        datasetname = str(datasetname.replace('/', '//'))
        
        coord_java = list(self.comp.spatialCoord())
        coord_labels = [str(coord_java[i]) for i in range(len(coord_java))]

        if self.geom.getSDim() == 2:
            if self.geom.isAxisymmetric():
                coord_labels = [coord_labels[0], coord_labels[2]]
            else:
                coord_labels = [coord_labels[0], coord_labels[1]]
        elif self.geom.getSDim() == 1:
            coord_labels = coord_labels[0]

        x, y = self.model_standalone.evaluate(coord_labels, dataset=datasetname)
        t = self.model_standalone.evaluate('t', unit='d', dataset=datasetname)
        t = np.unique(t)
        var_results = []
        var_eval = []
        for i in range(len(var_list)):
            var = self.model_standalone.evaluate(var_list[i], dataset=datasetname)
            var_eval.append(var)
            var_results.append([[] for _ in range(len(coords_list))])
        
        for n in tqdm(range(len(t)),desc="Processing time steps"):
            mesh_coords = np.array([x[n], y[n]]).T
            points_idx = []
            for i in range(len(coords_list)):
                distances = np.linalg.norm(mesh_coords - coords_list[i], axis=1)
                nearest_idx = np.argmin(distances)
                points_idx.append(nearest_idx)
                for k in range(len(var_list)):
                    var_results[k][i].append(var_eval[k][n][points_idx[i]])
        return t, var_results
    
    def point_evaluation_to_excel(self,
                                  dataset,
                                  var_list: list,
                                  point_list: list,
                                  order: int = 0,
                                  file_name: str = 'point_evaluation.xlsx',
                                  ):
        """
        Evaluate the variables at the specified points and save the results to an Excel file.

        Parameters:
            dataset (str or list): A dataset or a list of datasets to evaluate.
            var_list (list): A list of variables to evaluate. Or a list of lists of variables, one list for each dataset.
            point_list (list): A list of points to evaluate.
            order (int): The order of the evaluation. Defaults to 0. 0 stands for every point for each variable, and 1 for every variable for each point.
            file_name (str): The name of the Excel file to save the results. Defaults to 'point_evaluation.xlsx'.
        """
        if isinstance(dataset, str):
            dataset = [dataset]

        headlist = ['t']
        var_list_temp = var_list[0] if isinstance(var_list[0], list) else var_list
        if order == 0:
            for i, var in enumerate(var_list_temp):
                for j, point in enumerate(point_list):
                    headlist.append(f'{var}_{point}')
        elif order == 1:
            for i, point in enumerate(point_list):
                for j, var in enumerate(var_list_temp):
                    headlist.append(f'{point}_{var}')
        else:
            raise ValueError("order must be 0 or 1")
        
        df = pd.DataFrame(columns=headlist)

        for ds_idx, ds in enumerate(dataset):
            var_list_temp = var_list[ds_idx] if isinstance(var_list[0], list) else var_list
            df_temp = pd.DataFrame()
            t, var_results = self.get_variable_evolution_at_point(ds, var_list_temp, point_list)
            df_temp['t'] = t
            if order == 0:
                for i, var in enumerate(var_list_temp):
                    for j, point in enumerate(point_list):
                        df_temp[f'{var}_{point}'] = var_results[i][j]
            elif order == 1:
                for i, point in enumerate(point_list):
                    for j, var in enumerate(var_list_temp):
                        df_temp[f'{point}_{var}'] = var_results[j][i]
            else:
                raise ValueError("order must be 0 or 1")
            df_temp.columns = headlist
            df = pd.concat([df, df_temp], ignore_index=True)

        # Save to Excel
        logger.info(f"Saving results to {file_name}")
        df.to_excel(file_name, index=False)

        return df

    def get_dependent_variables(self,
                                solution: str | None = None,
                                dataset: str | None = None) -> list:
        """
        Get the dependent variables of a solution.

        Parameters:
            solution (str or None): The tag of the solution. If None, dataset must be given.
            dataset (str or None): The tag of the dataset. If None, solution must be given.

        Returns:
            list: A list of dependent variable names.
        """
        
        if solution is None:
            if dataset is None:
                raise ValueError("Either solution or dataset must be provided.")
            else:
                solution = self.model.result().dataset(dataset).getString('solution')

        var_list = []
        for i in self.model.sol(solution).feature('v1').feature().iterator():
            var_list.append(str(i.tag()).split('_',1)[1])

        self.variables = var_list
        return var_list

    def save(self, save_path: str = None):
        """
        Save the COMSOL model to a file.
        Parameters:
            save_path (str): The path to save the COMSOL model. If None, the original file path is overwritten.
        """
        if save_path is None: save_path = self.file_path
        logger.info(f"Saving COMSOL model to {save_path}")
        self.model.save(save_path, True)

    def __java_str__(self, obj):
        return jpype.JString(obj)
    
    def __java_double__(self, obj):
        return jpype.JDouble(obj)
    
    def __java_int__(self, obj):
        return jpype.JInt(obj)
    
    def __java_matrix__(self, obj):
        pass
    
    class ComsolExportPlot:
        def __init__(self,
                     width: int,
                     height: int,
                     resolution: int,
                     font_size: int,
                     ):
            """
            A class to handle the properties of a COMSOL plot export.
            Parameters:
                width (int): The width of the plot in pixels.
                height (int): The height of the plot in pixels.
                resolution (int): The resolution of the plot in dpi.
                font_size (int): The font size of the plot.
            """
            self.width = width
            self.height = height
            self.resolution = resolution
            self.font_size = font_size
 
    def run_derived_value(self,
                          derived_value_tag: str,
                          table_tag: str | None = None,
                          export_path: str | None = None,
                          ifexists: str = 'overwrite',
                          ):
        """
        Run a derived value and optionally export the results to a file.
        Arguments:
            derived_value_tag (str): The tag of the derived value to run.
            table_tag (str | None): The tag of the table to export the results to. If None, a new table is created.
            export_path (str | None): The path to export the results to. If None, the results are not exported.
            ifexists (str): What to do if the export file already exists. Options are 'overwrite' and 'append'. Defaults to 'overwrite'.
        """
        if table_tag is None:
            tables = self.model.result().table().tags()
            last_tag = max([int(re.findall(r'\d+', str(tag))[0]) for tag in tables if tag.startswith('tbl') and re.findall(r'\d+', str(tag))])
            table_tag = f'tbl{last_tag+1}'
            self.model.result().table().create(table_tag, 'Table')
        else:
            self.model.result().table(table_tag).clearTableData()
        
        logger.info(f"Running derived value {derived_value_tag}")
        self.model.result().numerical(derived_value_tag).set('table', table_tag)
        self.model.result().numerical(derived_value_tag).setResult()

        if export_path is not None:
            logger.info(f"Exporting derived value {derived_value_tag} to {export_path}")
            export_list = self.model.result().export().tags()
            if 'tbl1' in export_list:
                export = self.model.result().export('tbl1')
            else:
                export = self.model.result().export().create('tbl1', 'Table')
            export.set('header', False)
            export.set('table', table_tag)
            export.set('ifexists', ifexists)
            export.set('filename', export_path)
            export.run()
