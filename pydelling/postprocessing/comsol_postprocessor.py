import numpy as np
import pandas as pd
import mph
import re
import jpype
from tqdm import tqdm
import logging
from pathlib import Path

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

    class ComsolSurface:
        """
        A class to handle the properties of a COMSOL Surface.
        """
        def __init__(self,
                     expression: str,
                     unit: str | None = None,
                     dataset: str | None = None,
                     dataset_time: float | None = None,
                     color_table: str | None = None,
                     color_table_discrete: int | bool = False,
                     color_table_reverse: bool = False,
                     color_table_sym: bool = False,
                     rangelist: list | None = None,
                     selection: list | str | None = None,
                     ):
            """
            A class to handle the properties of a COMSOL Surface.
            Parameters:
                expression (str): The expression to plot.
                unit (str or None): The unit of the expression. If None default unit is used.
                dataset (str or None): The name of the dataset to use for the plot. If None, the template dataset is used.
                dataset_time (float or None): The time to use for the dataset, needed if dataset is not "parent". If None, the template time is used.
                color_table (str or None): The name of the color table to use for the plot. If None, the template color table is used.
                color_table_discrete (int or False): The number of discrete colors to use for the plot. If False, the color table is used as default.
                color_table_reverse (bool): If True, the color table is reversed. Defaults to False.
                color_table_sym (bool): If True, the color table is symmetric. Defaults to False.
                rangelist (list or None): The range of the plot. If None, automatic range is used.
                selection (list or str or None): A list of the domains in the selection. If 'all', all the domains are used. If a selection_tag is given, it is used. If None, the template selection is used.
            """
            self.expression = expression
            self.unit = unit
            self.dataset = dataset
            self.dataset_time = dataset_time
            self.color_table = color_table
            self.color_table_discrete = color_table_discrete
            self.color_table_reverse = color_table_reverse
            self.color_table_sym = color_table_sym
            self.rangelist = rangelist
            self.selection = selection
        
    class _PlotGroup1D:
        def __init__(self,
                     postprocessor: 'ComsolPostprocessor',
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
            A class to handle the properties of a COMSOL 1D Plot Group.
            Parameters:
                postprocessor: The COMSOL postprocessor object from ComsolPostprocessor.
                tag (str or None): The tag of the plot group to edit. If None, a new plot group is created. Defaults to None.
                dataset (str or None): The name of the dataset to use for the plot group. If None, dataset is not set. Defaults to None.
                label (str or None): The label of the plot group. If None, the label is not set. Defaults to None.
                time (list of float or "all" or "first" or "last" or None): The time steps to use for the plot group. If "all", all time steps are used. If None, time is not set. Defaults to None.
                xlabel (str or bool or None): The label of the x-axis. If False, automatic axis is used. If None, the label is not set. Defaults to None.
                ylabel (str or bool or None): The label of the y-axis. If False, automatic axis is used. If None, the label is not set. Defaults to None.
                xrange (list or None): The range of the x-axis. If None, automatic range is used. Defaults to None.
                yrange (list or None): The range of the y-axis. If None, automatic range is used. Defaults to None.
                xlog (bool or None): If True, the x-axis is logarithmic. If None, xlog is not set. Defaults to None.
                ylog (bool or None): If True, the y-axis is logarithmic. If None, ylog is not set. Defaults to None.
                axisprecision (int or None): The number of decimal places to use for the axis labels. If None, axisprecision is not set. Defaults to None.
                twoyaxes (bool or None): If True, a second y-axis is added to the plot. If None, twoyaxes is not set. Defaults to None.
                yseclabel (str or None): The label of the second y-axis. If None, the label is not set. Defaults to None.
                ysecrange (list or None): The range of the second y-axis. If None, automatic range is used. Defaults to None.
                yseclog (bool): If True, the second y-axis is logarithmic. Defaults to False.
                legendactive (bool): If True, the legend is shown. If None, legendactive is not set. Defaults to None.
                legendlayout (str or None): 'inside' or 'outside'. If None, the layout is not set. Defaults to None.
                legendpos (str or None): The position of the legend. If legend is inside, valid values are upperright | middleright | lowerright | upperleft | middleleft | lowerleft | middleright | center | middleleft. If legend is outside, valid values are bottom | top | left | right. If None, the position is not set. Defaults to None.
                legendcolumncount (int or None): The number of columns in the legend. When legendpos is top or bottom, legendcolumncount stands for the number of rows. If None, the number of columns is not set. Defaults to None.
            Returns:
                A Comsol API PlotGroup1D object.
            """
            self.postprocessor = postprocessor
            self.model = postprocessor.model
            self.dataset = dataset
            self.label = label
            self.time = time
            self.xlabel = xlabel
            self.ylabel = ylabel
            self.xrange = xrange
            self.yrange = yrange
            self.xlog = xlog
            self.ylog = ylog
            self.axisprecision = axisprecision
            self.twoyaxes = twoyaxes
            self.yseclabel = yseclabel
            self.ysecrange = ysecrange
            self.yseclog = yseclog
            self.legendactive = legendactive
            self.legendlayout = legendlayout
            self.legendpos = legendpos
            self.legendcolumncount = legendcolumncount
            self.childs = []

            if tag is None:
                tags = self.model.result().tags()
                last_tag = max([int(re.findall(r'\d+', str(temptag))[0]) for temptag in tags if re.findall(r'\d+', str(temptag))])
                tag = f'pg{last_tag+1}'
                self.tag = tag
                self._api = self.model.result().create(self.tag, 'PlotGroup1D')
                self.postprocessor.childs.append(self)
                logger.info(f"1D Plot Group {self.tag} created.")
            else:
                self.tag = tag
                self._api = self.model.result(self.tag)
                self.postprocessor.childs.append(self)
                logger.info(f"1D Plot Group {self.tag} loaded.")
                for child_tag in self._api.feature().tags():
                    child_type = self._api.feature(child_tag).getType()
                    if child_type == 'LineGraph':
                        self.line_graph(tag=child_tag)
                    elif child_type == 'PointGraph':
                        self.point_graph(tag=child_tag)
                    else:
                        logger.warning(f"Feature type {child_type} in {child_tag} not recognized.")
                        self.childs.append(child_type)

            self.apply()
        
        def apply(self):
            """
            Apply the changes of the PlotGroup1D to the COMSOL API model.
            """
            if self.dataset is not None: self._api.set('data', self.dataset)
            if self.label is not None: self._api.label(self.label)
            if self.time is not None:
                if self.time == 'all':
                    self._api.set('innerinput', 'all')
                if self.time == 'first':
                    self._api.set('looplevelinput','first')
                if self.time == 'last':
                    self._api.set('looplevelinput','last')
                else:
                    for n in range(len(self.time)):
                        self.time[n] = float(self.time[n])
                    self._api.set('t', self.time)
            if self.xlabel is not None: self._api.set('xlabel', self.xlabel)
            if self.ylabel is not None: self._api.set('ylabel', self.ylabel)
            if self.xrange is not None:
                if self.xrange == False:
                    self._api.set('axislimits', 'off')
                else:
                    self._api.set('axislimits', 'on')
                    self._api.set('xmin', self.postprocessor.__java_double__(self.xrange[0]))
                    self._api.set('xmax', self.postprocessor.__java_double__(self.xrange[1]))
            if self.yrange is not None:
                if self.yrange == False:
                    self._api.set('axislimits', 'off')
                else:
                    self._api.set('axislimits', 'on')
                    self._api.set('ymin', self.postprocessor.__java_double__(self.yrange[0]))
                    self._api.set('ymax', self.postprocessor.__java_double__(self.yrange[1]))
            if self.xlog: self._api.set('xlog', 'on')
            else: self._api.set('xlog', 'off')
            if self.ylog: self._api.set('ylog', 'on')
            else: self._api.set('ylog', 'off')
            if self.axisprecision is not None: self._api.set('axisprecision', self.postprocessor.__java_int__(self.axisprecision))
            if self.twoyaxes is not None: self._api.set('twoyaxes', self.twoyaxes)
            if self.yseclabel is not None: self._api.set('yseclabel', self.yseclabel)
            if self.ysecrange is not None:
                self._api.set('yminsec', self.postprocessor.__java_double__(self.ysecrange[0]))
                self._api.set('ymaxsec', self.postprocessor.__java_double__(self.ysecrange[1]))
            if self.yseclog: self._api.set('ylogsec', 'on')
            else: self._api.set('ylogsec', 'off')
            if self.legendactive is not None:
                if self.legendactive: self._api.set('legendactive', 'on')
                else: self._api.set('legendactive', 'off')
            if self.legendlayout is not None: self._api.set('legendlayout', self.legendlayout)
            if self.legendpos is not None:
                legendlayout = self.legendlayout
                if self.legendlayout is None:
                    legendlayout = self._api.getString('legendlayout')
                if legendlayout == 'inside':
                    self._api.set('legendpos', self.legendpos)
                if legendlayout == 'outside':
                    self._api.set('legendposoutside', self.legendpos)
            if self.legendcolumncount is not None:
                if self.legendpos in ['top', 'bottom']:
                    self._api.set('legendrowcount', self.postprocessor.__java_int__(self.legendcolumncount))
                elif self.legendpos is None:
                    if self._api.getString('legendposoutside') in ['top', 'bottom']:
                        self._api.set('legendrowcount', self.postprocessor.__java_int__(self.legendcolumncount))
                self._api.set('legendcolumncount', self.postprocessor.__java_int__(self.legendcolumncount))

            for child in self.childs:
                child.apply()

        def run(self):
            """
            Run the PlotGroup1D to update the plot.
            """
            logger.info(f"Running 1D Plot Group {self.tag}...")
            self._api.run()
            logger.info(f"1D Plot Group {self.tag} run completed.")

        def duplicate(self):
            """
            Duplicates the Plot Group
            Returns:
                A PlotGroup1D object.
            """
            tags = self.model.result().tags()
            last_tag = max([int(re.findall(r'\d+', str(tag))[0]) for tag in tags if re.findall(r'\d+', str(tag))])
            logger.info(f"Duplicating Plot Group {self.tag} to pg{last_tag+1}...")
            self.model.result().duplicate(f'pg{last_tag+1}', self.tag)
            plot_group = self.postprocessor.plot_group_1D(tag=f'pg{last_tag+1}')
            return plot_group

        def export(self,
                   export_path: str | None = None):
            """
            Export the PlotGroup1D to a PNG file.
            Parameters:
                export_path (str or None): The path to save the PNG file. If None, the file is saved in the current directory with the name of the plot group tag. Defaults to None.
            Warning:
                If the ComsolPostprocessor.export_properties() is not used, the export properties will be the default ones.
            """
            self._api.run()
            file_parent = Path(self.postprocessor.file_path).parent
            if export_path is None: export_path = f"{file_parent}/{self.tag}.png"
            self.postprocessor._export(self.tag, export_path)


        class _LineGraph:
            """
            A class to handle the properties of a COMSOL Line Graph.
            """
            def __init__(self,
                         plotgroup: 'ComsolPostprocessor._PlotGroup1D',
                            tag: str | None = None,
                            expression: str | None = None,
                            unit: str | None = None,
                            dataset: str | None = None,
                            dataset_param: str | None = None,
                            dataset_time: list[float] | str | None = None,
                            selection: str | list | None = None,
                            xdata: str | None = None,
                            xdataexpr: str | None = None,
                            xdataunit: str | None = None,
                            linecolor: str | None = None,
                            colorcycle: str | None = None,
                            linestyle: str | None = None,
                            linewidth: float | None = None,
                            marker: str | None = None,
                            plotonsecyaxis: bool | None = None,
                            legend: bool | None = None,
                            legendmethod: str | None = None,
                            legendmanuallist: list | None = None,
                            legendprefix: str | None = None,
                            legendsuffix: str | None = None,
                            legendpattern: str | None = None,
                            legendexprprecision: int | None = None,
                            ):
                """
                A class to handle the properties of a COMSOL Line Graph.
                Parameters:
                    plotgroup: The COMSOL PlotGroup1D object from ComsolPostprocessor._PlotGroup1D.
                    tag (str or None): The tag of the line graph to edit. If None, a new line graph is created. Defaults to None.
                    expression (str or None): The expression to plot. If None, the expression is not set. Defaults to None.
                    unit (str or None): The unit of the expression. If None, unit is not set. Defaults to None.
                    dataset (str or None): The name of the dataset to use for the plot. If None, dataset is not set. Defaults to None.
                    dataset_param (str or None): The parameter to use for the dataset, needed if dataset is not "parent". Valid values are "parent" or "manual". If None, dataset_param is not set. Defaults to None.
                    dataset_time (list of float or "all" or "first" or "last" or None): The time steps to use for the dataset, needed if dataset_param is not "parent". If None, time is not set. Defaults to None.
                    selection (str or list or None): The list of lines to plot. If "all", all lines are plotted. If a Explicit Selection tag is given, it is used. If None, the selection is not set. Defaults to None.
                    xdata (str or None): Can be "arc" or "expr". If None, the default x-axis is used. Defaults to None.
                    xdataexpr (str or None): The expression to use for the x-axis if xdata is "expr". If None, the default x-axis is used. Defaults to None.
                    xdataunit (str or None): The unit of the x-axis expression. If None, default unit is used. Defaults to None.
                    linecolor (str or None): The color of the line. Valid values are "cycle", "cyclereset", "black", "blue", "gray", "green", "magenta", "red", "white" and "yellow". If None, linecolor is not set. Defaults to None.
                    colorcycle (str or None): The color cycle to use for the line. Valid values are "default" or "long". If None, color cycle is not set. Defaults to None.
                    linestyle (str or None): The style of the line. Valid values are "none", "cycle", "solid", "dashed", "dotted" and "dashdot". If None, linestyle is not set. Defaults to None.
                    linewidth (float or None): The width of the line in points. If None, linewidth is not set. Defaults to None.
                    marker (str or None): The marker to use for the line. Valid values are "none", "cycle", "asterisk", "circle", "diamond", "plus", "point", "square", "star" and "triangle". Color and width are the same than linecolor and linewidth. If None, marker is not set. Defaults to None.
                    plotonsecyaxis (bool or None): If True, the line is plotted on the secondary y-axis. If None, plotonsecyaxis is not set. Defaults to None.
                    legend (bool or None): If True, the legend is shown for this line. If None, the default legend setting is used. Defaults to None.
                    legendmethod (str or None): Valid values are "automatic", "manual" or "evaluated". If None, legendmethod is not set. Defaults to None.
                    legendmanualist (list or None): A list of strings to use for the legend when legendmethod is "manual". If None, legendmanualist is not set. Defaults to None.
                    legendprefix (str or None): A string to prefix the legend when legendmethod is "automatic". If None, legendprefix is not set. Defaults to None.
                    legendsuffix (str or None): A string to suffix the legend when legendmethod is "automatic". If None, legendsuffix is not set. Defaults to None.
                    legendpattern (str or None): A pattern to use for the legend when legendmethod is "evaluated". If None, legendpattern is not set. Defaults to None.
                    legendexprprecision (int or None): The number of decimal places to use for evaluated expressions in the legend when legendmethod is "evaluated". If None, legendexprprecision is not set. Defaults to None.
                """
                self.plotgroup = plotgroup
                self.postprocessor = self.plotgroup.postprocessor
                self.model = self.postprocessor.model
                self.expression = expression
                self.unit = unit
                self.dataset = dataset
                self.dataset_param = dataset_param
                self.dataset_time = dataset_time
                self.selection = selection
                self.xdata = xdata
                self.xdataexpr = xdataexpr
                self.xdataunit = xdataunit
                self.linecolor = linecolor
                self.colorcycle = colorcycle
                self.linestyle = linestyle
                self.linewidth = linewidth
                self.marker = marker
                self.plotonsecyaxis = plotonsecyaxis
                self.legend = legend
                self.legendmethod = legendmethod
                self.legendmanuallist = legendmanuallist
                self.legendprefix = legendprefix
                self.legendsuffix = legendsuffix
                self.legendpattern = legendpattern
                self.legendexprprecision = legendexprprecision
                
                if tag is None:
                    tags = self.plotgroup._api.feature().tags()
                    try :last_tag = max([int(re.findall(r'\d+', str(temptag))[0]) for temptag in tags if re.findall(r'lngr\d+', str(temptag))])
                    except: last_tag = 0
                    tag = f'lngr{last_tag+1}'
                    self.tag = tag
                    self._api = self.model.result(self.plotgroup.tag).create(self.tag, 'LineGraph')
                    self.plotgroup.childs.append(self)
                    logger.info(f"Line Graph {self.tag} created.")
                else:
                    self.tag = tag
                    self._api = self.model.result(self.plotgroup.tag).feature(self.tag)
                    self.plotgroup.childs.append(self)
                    logger.info(f"Line Graph {self.tag} loaded.")
                    
                self.apply()

            def apply(self):
                """
                Apply the changes of the LineGraph to the COMSOL API model.
                """
                if self.dataset is not None: self._api.set('data', self.dataset)
                if self.expression is not None: self._api.set('expr', self.expression)
                if self.unit is not None: self._api.set('unit', self.unit)
                if self.dataset_param is not None: self._api.set('solutionparams', self.dataset_param)
                if self.dataset_time is not None:
                    if self.dataset_time == 'all':
                        self._api.set('innerinput', 'all')
                    if self.dataset_time == 'first':
                        self._api.set('looplevelinput','first')
                    if self.dataset_time == 'last':
                        self._api.set('looplevelinput','last')
                    else:
                        for n in range(len(self.dataset_time)):
                            self.dataset_time[n] = float(self.dataset_time[n])
                        self._api.set('t', self.dataset_time)
                if self.dataset_time == 'first':
                    self._api.set('looplevelinput','first')
                if self.dataset_time == 'last':
                    self._api.set('looplevelinput','last')
                if self.selection is not None:
                    if self.selection == 'all':
                        self._api.selection().all()
                    elif isinstance(self.selection, str):
                        self._api.selection().named(self.selection)
                    elif isinstance(self.selection, list):                        
                        self._api.selection().set(self.selection)
                    else:
                        raise ValueError("Selection must be 'all', a selection tag (str) or a list of integers.")
                if self.xdata is not None: self._api.set('xdata', self.xdata)
                if self.xdataexpr is not None:self._api.set('xdataexpr', self.xdataexpr)
                if self.xdataunit is not None: self._api.set('xdataunit', self.xdataunit)
                if self.linecolor is not None: self._api.set('linecolor', self.linecolor)
                if self.colorcycle is not None: self._api.set('colorcycle', self.colorcycle)
                if self.linestyle is not None: self._api.set('linestyle', self.linestyle)
                if self.linewidth is not None: self._api.set('linewidth', self.postprocessor.__java_double__(self.linewidth))
                if self.marker is not None:
                    self._api.set('linemarker', self.marker)
                    self._api.set('markerpos', 'datapoints')
                if self.plotonsecyaxis is not None: self._api.set('plotonsecyaxis', self.plotonsecyaxis)
                if self.legend is not None:
                    if self.legend: self._api.set('legend', 'on')
                    else: self._api.set('legend', 'off')
                if self.legendmethod is not None: self._api.set('legendmethod', self.legendmethod)
                if self.legendmanuallist is not None: self._api.set('legends', self.legendmanuallist)
                if self.legendprefix is not None: self._api.set('legendprefix', self.legendprefix)
                if self.legendsuffix is not None: self._api.set('legendsuffix', self.legendsuffix)
                if self.legendpattern is not None: self._api.set('legendpattern', self.legendpattern)
                if self.legendexprprecision is not None: self._api.set('legendexprprecision', self.postprocessor.__java_int__(self.legendexprprecision))
                
        def line_graph(self,
                        tag: str | None = None,
                            expression: str | None = None,
                            unit: str | None = None,
                            dataset: str | None = None,
                            dataset_param: str | None = None,
                            dataset_time: list[float] | str | None = None,
                            selection: str | list | None = None,
                            xdata: str | None = None,
                            xdataexpr: str | None = None,
                            xdataunit: str | None = None,
                            linecolor: str | None = None,
                            colorcycle: str | None = None,
                            linestyle: str | None = None,
                            linewidth: float | None = None,
                            marker: str | None = None,
                            plotonsecyaxis: bool | None = None,
                            legend: bool | None = None,
                            legendmethod: str | None = None,
                            legendmanuallist: list | None = None,
                            legendprefix: str | None = None,
                            legendsuffix: str | None = None,
                            legendpattern: str | None = None,
                            legendexprprecision: int | None = None,
                            ):
            """
            A class to handle the properties of a COMSOL Line Graph.
            Parameters:
                tag (str or None): The tag of the line graph to edit. If None, a new line graph is created. Defaults to None.
                expression (str or None): The expression to plot. If None, the expression is not set. Defaults to None.
                unit (str or None): The unit of the expression. If None, unit is not set. Defaults to None.
                dataset (str or None): The name of the dataset to use for the plot. If None, dataset is not set. Defaults to None.
                dataset_param (str or None): The parameter to use for the dataset, needed if dataset is not "parent". Valid values are "parent" or "manual". If None, dataset_param is not set. Defaults to None.
                dataset_time (list of float or "all" or "first" or "last" or None): The time steps to use for the dataset, needed if dataset_param is not "parent". If None, time is not set. Defaults to None.
                selection (str or list or None): The list of lines to plot. If "all", all lines are plotted. If a Explicit Selection tag is given, it is used. If None, the selection is not set. Defaults to None.
                xdata (str or None): Can be "arc" or "expr". If None, the default x-axis is used. Defaults to None.
                xdataexpr (str or None): The expression to use for the x-axis if xdata is "expr". If None, the default x-axis is used. Defaults to None.
                xdataunit (str or None): The unit of the x-axis expression. If None, default unit is used. Defaults to None.
                linecolor (str or None): The color of the line. Valid values are "cycle", "cyclereset", "black", "blue", "gray", "green", "magenta", "red", "white" and "yellow". If None, linecolor is not set. Defaults to None.
                colorcycle (str or None): The color cycle to use for the line. Valid values are "default" or "long". If None, color cycle is not set. Defaults to None.
                linestyle (str or None): The style of the line. Valid values are "none", "cycle", "solid", "dashed", "dotted" and "dashdot". If None, linestyle is not set. Defaults to None.
                linewidth (float or None): The width of the line in points. If None, linewidth is not set. Defaults to None.
                marker (str or None): The marker to use for the line. Valid values are "none", "cycle", "asterisk", "circle", "diamond", "plus", "point", "square", "star" and "triangle". Color and width are the same than linecolor and linewidth. If None, marker is not set. Defaults to None.
                plotonsecyaxis (bool or None): If True, the line is plotted on the secondary y-axis. If None, plotonsecyaxis is not set. Defaults to None.
                legend (bool or None): If True, the legend is shown for this line. If None, the default legend setting is used. Defaults to None.
                legendmethod (str or None): Valid values are "automatic", "manual" or "evaluated". If None, legendmethod is not set. Defaults to None.
                legendmanualist (list or None): A list of strings to use for the legend when legendmethod is "manual". If None, legendmanualist is not set. Defaults to None.
                legendprefix (str or None): A string to prefix the legend when legendmethod is "automatic". If None, legendprefix is not set. Defaults to None.
                legendsuffix (str or None): A string to suffix the legend when legendmethod is "automatic". If None, legendsuffix is not set. Defaults to None.
                legendpattern (str or None): A pattern to use for the legend when legendmethod is "evaluated". If None, legendpattern is not set. Defaults to None.
                legendexprprecision (int or None): The number of decimal places to use for evaluated expressions in the legend when legendmethod is "evaluated". If None, legendexprprecision is not set. Defaults to None.
            Returns:
                A LineGraph object.
            """
            linegraph = self._LineGraph(self, tag, expression, unit, dataset, dataset_param, dataset_time, selection, xdata, xdataexpr, xdataunit, linecolor, colorcycle, linestyle, linewidth, marker, plotonsecyaxis, legend, legendmethod, legendmanuallist, legendprefix, legendsuffix, legendpattern, legendexprprecision)
            return linegraph
        
        class _PointGraph:
            """
            A class to handle the properties of a COMSOL Point Graph.
            """
            def __init__(self,
                         plotgroup: 'ComsolPostprocessor._PlotGroup1D',
                            tag: str | None = None,
                            expression: str | None = None,
                            unit: str | None = None,
                            dataset: str | None = None,
                            dataset_param: str | None = None,
                            dataset_time: list[float] | str | None = None,
                            selection: str | list | None = None,
                            xdata: str | None = None,
                            xdataexpr: str | None = None,
                            xdataunit: str | None = None,
                            linecolor: str | None = None,
                            colorcycle: str | None = None,
                            linestyle: str | None = None,
                            linewidth: float | None = None,
                            marker: str | None = None,
                            plotonsecyaxis: bool | None = None,
                            legend: bool | None = None,
                            legendmethod: str | None = None,
                            legendmanuallist: list | None = None,
                            legendprefix: str | None = None,
                            legendsuffix: str | None = None,
                            legendpattern: str | None = None,
                            legendexprprecision: int | None = None,
                            ):
                """
                A class to handle the properties of a COMSOL Point Graph.
                Parameters:
                    plotgroup: The COMSOL PlotGroup1D object from ComsolPostprocessor._PlotGroup1D.
                    tag (str or None): The tag of the point graph to edit. If None, a new point graph is created. Defaults to None.
                    expression (str or None): The expression to plot. If None, the expression is not set. Defaults to None.
                    unit (str or None): The unit of the expression. If None default unit is used.
                    dataset (str or None): The name of the dataset to use for the plot. If None, dataset is not set. Defaults to None.
                    dataset_param (str or None): The parameter to use for the dataset, needed if dataset is not "parent". Valid values are "parent" or "manual". If None, dataset_param is not set. Defaults to None.
                    dataset_time (list of float or 'all' or 'first' or 'last' or None): The time steps to use for the dataset, needed if dataset_param is not "parent". If None, time is not set. Defaults to None.
                    selection (str or list or None): The list of lines to plot. If "all", all lines are plotted. If a Explicit Selection tag is given, it is used. If None, the selection is not set. Defaults to None.
                    xdata (str or None): Can be "arc" or "expr". If None, the default x-axis is used. Defaults to None.
                    xdataexpr (str or None): The expression to use for the x-axis if xdata is "expr". If None, the default x-axis is used. Defaults to None.
                    xdataunit (str or None): The unit of the x-axis expression. If None, default unit is used. Defaults to None.
                    linecolor (str or None): The color of the line. Valid values are "cycle", "cyclereset", "black", "blue", "gray", "green", "magenta", "red", "white" and "yellow". If None, linecolor is not set. Defaults to None.
                    colorcycle (str or None): The color cycle to use for the line. Valid values are "default" or "long". If None, colorcycle is not set. Defaults to None.
                    linestyle (str or None): The style of the line. Valid values are "none", "cycle", "solid", "dashed", "dotted" and "dashdot". If None, linestyle is not set. Defaults to None.
                    linewidth (float or None): The width of the line in points. If None, linewidth is not set. Defaults to None.
                    marker (str or None): The marker to use for the line. Valid values are "none", "cycle", "asterisk", "circle", "diamond", "plus", "point", "square", "star" and "triangle". Color and width are the same than linecolor and linewidth. If None, marker is not set. Defaults to None.
                    plotonsecyaxis (bool or None): If True, the line is plotted on the secondary y-axis. If None, plotonsecyaxis is not set. Defaults to None.
                    legend (bool or None): If True, the legend is shown for this line. If None, the default legend setting is used. Defaults to None.
                    legendmethod (str or None): Valid values are "automatic", "manual" or "evaluated". If None, legendmethod is not set. Defaults to None.
                    legendmanualist (list or None): A list of strings to use for the legend when legendmethod is "manual". If None, legendmanualist is not set. Defaults to None.
                    legendprefix (str or None): A string to prefix the legend when legendmethod is "automatic". If None, legendprefix is not set. Defaults to None.
                    legendsuffix (str or None): A string to suffix the legend when legendmethod is "automatic". If None, legendsuffix is not set. Defaults to None.
                    legendpattern (str or None): A pattern to use for the legend when legendmethod is "evaluated". If None, legendpattern is not set. Defaults to None.
                    legendexprprecision (int or None): The number of decimal places to use for evaluated expressions in the legend when legendmethod is "evaluated". If None, legendexprprecision is not set. Defaults to None.
                """
                self.plotgroup = plotgroup
                self.postprocessor = self.plotgroup.postprocessor
                self.model = self.postprocessor.model
                self.expression = expression
                self.unit = unit
                self.dataset = dataset
                self.dataset_param = dataset_param
                self.dataset_time = dataset_time
                self.selection = selection
                self.xdata = xdata
                self.xdataexpr = xdataexpr
                self.xdataunit = xdataunit
                self.linecolor = linecolor
                self.colorcycle = colorcycle
                self.linestyle = linestyle
                self.linewidth = linewidth
                self.marker = marker
                self.plotonsecyaxis = plotonsecyaxis
                self.legend = legend
                self.legendmethod = legendmethod
                self.legendmanuallist = legendmanuallist
                self.legendprefix = legendprefix
                self.legendsuffix = legendsuffix
                self.legendpattern = legendpattern
                self.legendexprprecision = legendexprprecision
                
                if tag is None:
                    tags = self.plotgroup._api.feature().tags()
                    try :last_tag = max([int(re.findall(r'\d+', str(temptag))[0]) for temptag in tags if re.findall(r'ptgr\d+', str(temptag))])
                    except: last_tag = 0
                    tag = f'ptgr{last_tag+1}'
                    self.tag = tag
                    self._api = self.model.result(self.plotgroup.tag).create(self.tag, 'PointGraph')
                    self.plotgroup.childs.append(self)
                    logger.info(f"Point Graph {self.tag} created.")
                else:
                    self.tag = tag
                    self._api = self.model.result(self.plotgroup.tag).feature(self.tag)
                    self.plotgroup.childs.append(self)
                    logger.info(f"Point Graph {self.tag} loaded.")

                self.apply()

            def apply(self):
                """
                Apply the changes of the PointGraph to the COMSOL API model.
                """
                if self.dataset is not None: self._api.set('data', self.dataset)
                if self.expression is not None: self._api.set('expr', self.expression)
                if self.unit is not None: self._api.set('unit', self.unit)
                if self.dataset_param is not None: self._api.set('solutionparams', self.dataset_param)
                if self.dataset_time is not None:
                    if self.dataset_time == 'all':
                        self._api.set('innerinput', 'all')
                    if self.dataset_time == 'first':
                        self._api.set('looplevelinput','first')
                    if self.dataset_time == 'last':
                        self._api.set('looplevelinput','last')
                    else:
                        for n in range(len(self.dataset_time)):
                            self.dataset_time[n] = float(self.dataset_time[n])
                        self._api.set('t', self.dataset_time)
                if self.selection is not None:
                    if self.selection == 'all':
                        self._api.selection().all()
                    elif isinstance(self.selection, str):
                        self._api.selection().named(self.selection)
                    elif isinstance(self.selection, list):                        
                        self._api.selection().set(self.selection)
                    else:
                        raise ValueError("Selection must be 'all', a selection tag (str) or a list of integers.")
                if self.xdata is not None: self._api.set('xdata', self.xdata)
                if self.xdataexpr is not None:self._api.set('xdataexpr', self.xdataexpr)
                if self.xdataunit is not None: self._api.set('xdataunit', self.xdataunit)
                if self.linecolor is not None: self._api.set('linecolor', self.linecolor)
                if self.colorcycle is not None: self._api.set('colorcycle', self.colorcycle)
                if self.linestyle is not None: self._api.set('linestyle', self.linestyle)
                if self.linewidth is not None: self._api.set('linewidth', self.postprocessor.__java_double__(self.linewidth))
                if self.marker is not None:
                    self._api.set('linemarker', self.marker)
                    self._api.set('markerpos', 'datapoints')
                if self.plotonsecyaxis is not None: self._api.set('plotonsecyaxis', self.plotonsecyaxis)
                if self.legend is not None:
                    if self.legend: self._api.set('legend', 'on')
                    else: self._api.set('legend', 'off')
                if self.legendmethod is not None: self._api.set('legendmethod', self.legendmethod)
                if self.legendmanuallist is not None: self._api.set('legends', self.legendmanuallist)
                if self.legendprefix is not None: self._api.set('legendprefix', self.legendprefix)
                if self.legendsuffix is not None: self._api.set('legendsuffix', self.legendsuffix)
                if self.legendpattern is not None: self._api.set('legendpattern', self.legendpattern)
                if self.legendexprprecision is not None: self._api.set('legendexprprecision', self.postprocessor.__java_int__(self.legendexprprecision))
                
        def point_graph(self,
                        tag: str | None = None,
                        expression: str | None = None,
                        unit: str | None = None,
                        dataset: str | None = None,
                        dataset_param: str | None = None,
                        dataset_time: list[float] | str | None = None,
                        selection: str | list | None = None,
                        xdata: str | None = None,
                        xdataexpr: str | None = None,
                        xdataunit: str | None = None,
                        linecolor: str | None = None,
                        colorcycle: str | None = None,
                        linestyle: str | None = None,
                        linewidth: float | None = None,
                        marker: str | None = None,
                        plotonsecyaxis: bool | None = None,
                        legend: bool | None = None,
                        legendmethod: str | None = None,
                        legendmanuallist: list | None = None,
                        legendprefix: str | None = None,
                        legendsuffix: str | None = None,
                        legendpattern: str | None = None,
                        legendexprprecision: int | None = None,
                        ):
            """
            A class to handle the properties of a COMSOL Point Graph.
            Parameters:
                tag (str or None): The tag of the point graph to edit. If None, a new point graph is created. Defaults to None.
                expression (str or None): The expression to plot. If None, the expression is not set. Defaults to None.
                unit (str or None): The unit of the expression. If None default unit is used.
                dataset (str or None): The name of the dataset to use for the plot. If None, dataset is not set. Defaults to None.
                dataset_param (str or None): The parameter to use for the dataset, needed if dataset is not "parent". Valid values are "parent" or "manual". If None, dataset_param is not set. Defaults to None.
                dataset_time (list of float or 'all' or 'first' or 'last' or None): The time steps to use for the dataset, needed if dataset_param is not "parent". If None, time is not set. Defaults to None.
                selection (str or list or None): The list of lines to plot. If "all", all lines are plotted. If a Explicit Selection tag is given, it is used. If None, the selection is not set. Defaults to None.
                xdata (str or None): Can be "arc" or "expr". If None, the default x-axis is used. Defaults to None.
                xdataexpr (str or None): The expression to use for the x-axis if xdata is "expr". If None, the default x-axis is used. Defaults to None.
                xdataunit (str or None): The unit of the x-axis expression. If None, default unit is used. Defaults to None.
                linecolor (str or None): The color of the line. Valid values are "cycle", "cyclereset", "black", "blue", "gray", "green", "magenta", "red", "white" and "yellow". If None, linecolor is not set. Defaults to None.
                colorcycle (str or None): The color cycle to use for the line. Valid values are "default" or "long". If None, colorcycle is not set. Defaults to None.
                linestyle (str or None): The style of the line. Valid values are "none", "cycle", "solid", "dashed", "dotted" and "dashdot". If None, linestyle is not set. Defaults to None.
                linewidth (float or None): The width of the line in points. If None, linewidth is not set. Defaults to None.
                marker (str or None): The marker to use for the line. Valid values are "none", "cycle", "asterisk", "circle", "diamond", "plus", "point", "square", "star" and "triangle". Color and width are the same than linecolor and linewidth. If None, marker is not set. Defaults to None.
                plotonsecyaxis (bool or None): If True, the line is plotted on the secondary y-axis. If None, plotonsecyaxis is not set. Defaults to None.
                legend (bool or None): If True, the legend is shown for this line. If None, the default legend setting is used. Defaults to None.
                legendmethod (str or None): Valid values are "automatic", "manual" or "evaluated". If None, legendmethod is not set. Defaults to None.
                legendmanualist (list or None): A list of strings to use for the legend when legendmethod is "manual". If None, legendmanualist is not set. Defaults to None.
                legendprefix (str or None): A string to prefix the legend when legendmethod is "automatic". If None, legendprefix is not set. Defaults to None.
                legendsuffix (str or None): A string to suffix the legend when legendmethod is "automatic". If None, legendsuffix is not set. Defaults to None.
                legendpattern (str or None): A pattern to use for the legend when legendmethod is "evaluated". If None, legendpattern is not set. Defaults to None.
                legendexprprecision (int or None): The number of decimal places to use for evaluated expressions in the legend when legendmethod is "evaluated". If None, legendexprprecision is not set. Defaults to None.
            Returns:
                A PointGraph object.
            """
            pointgraph = self._PointGraph(self, tag, expression, unit, dataset, dataset_param, dataset_time, selection, xdata, xdataexpr, xdataunit, linecolor, colorcycle, linestyle, linewidth, marker, plotonsecyaxis, legend, legendmethod, legendmanuallist, legendprefix, legendsuffix, legendpattern, legendexprprecision)
            return pointgraph

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
        plotgroup = self._PlotGroup1D(
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

    class _PlotGroup2D:
        def __init__(self,
                     postprocessor: 'ComsolPostprocessor',
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
                postprocessor: The COMSOL Postprocessor object from ComsolPostprocessor.
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
            """
            self.postprocessor = postprocessor
            self.model = self.postprocessor.model
            self.dataset = dataset
            self.label = label
            self.time = time
            self.selection = selection
            self.view = view
            self.showlegends = showlegends
            self.legendcolor = legendcolor
            self.legendpos = legendpos
            self.showlegendsmaxmin = showlegendsmaxmin
            self.showlegendsunit = showlegendsunit
            self.legendformattingactive = legendformattingactive
            self.legendnotation = legendnotation
            self.legendprecision = legendprecision
            self.childs = []

            if tag is None:
                tags = self.model.result().tags()
                last_tag = max([int(re.findall(r'\d+', str(temptag))[0]) for temptag in tags if re.findall(r'\d+', str(temptag))])
                tag = f'pg{last_tag+1}'
                self.tag = tag
                self._api = self.model.result().create(self.tag, 'PlotGroup2D')
                self.postprocessor.childs.append(self)
                logger.info(f"2D Plot Group {self.tag} created.")
            else:
                self.tag = tag
                self._api = self.model.result(self.tag)
                self.postprocessor.childs.append(self)
                logger.info(f"2D Plot Group {self.tag} loaded.")
                for child_tag in self._api.feature().tags():
                    child_type = self._api.feature(child_tag).getType()
                    if child_type == 'Surface':
                        self.surface(tag=child_tag)
                    else:
                        logger.warning(f"Feature type {child_type} in {child_tag} not recognized.")
                        self.childs.append(child_type)

            self.apply()

        def apply(self):
            """
            Apply the changes of the PlotGroup2D to the COMSOL API model.
            """
            if self.dataset is not None: self._api.set('data', self.dataset)
            if self.label is not None: self._api.label(self.label)
            if self.time is not None:
                    if self.time == 'all':
                        self._api.set('innerinput', 'all')
                    else:
                        self._api.set('t', float(self.time))
            if self.selection is not None:
                if self.selection == 'all':
                    self._api.selection().allGeom()
                elif isinstance(self.selection, str):
                    self._api.selection().named(self.selection)
                elif isinstance(self.selection, list):                        
                    self._api.selection().set(self.selection)
                else:
                    raise ValueError("Selection must be 'all', a selection tag (str) or a list of integers.")
            if self.view is not None: self._api.set('view', self.view)
            if self.showlegends is not None:
                if self.showlegends: self._api.set('showlegends', 'on')
                else: self._api.set('showlegends', 'off')
            if self.legendcolor is not None: self._api.set('legendcolor', self.legendcolor)
            if self.legendpos is not None: self._api.set('legendpos', self.legendpos)
            if self.showlegendsmaxmin is not None: self._api.set('showlegendsmaxmin', self.showlegendsmaxmin)
            if self.showlegendsunit is not None: self._api.set('showlegendsunit', self.showlegendsunit)
            if self.legendformattingactive is not None: self._api.set('legendactive', self.legendformattingactive)
            if self.legendnotation is not None: self._api.set('legendnotation', self.legendnotation)
            if self.legendprecision is not None: self._api.set('legendprecision', self.postprocessor.__java_int__(self.legendprecision))

            for child in self.childs:
                child.apply()

        def run(self):
            """
            Run the plot group to generate the plot.
            """
            logger.info(f"Running 2D Plot Group {self.tag}.")
            self._api.run()
            logger.info(f"2D Plot Group {self.tag} run completed.")
        
        def duplicate(self):
            """
            Duplicate the plot group. 
            Returns:
                A PlotGroup2D object.
            """
            tags = self.model.result().tags()
            last_tag = max([int(re.findall(r'\d+', str(tag))[0]) for tag in tags if re.findall(r'\d+', str(tag))])
            logger.info(f"Duplicating Plot Group {self.tag} to pg{last_tag+1}...")
            self.model.result().duplicate(f'pg{last_tag+1}', self.tag)
            plot_group = self.postprocessor.plot_group_2D(tag=f'pg{last_tag+1}')
            return plot_group
    
        def export(self,
                   export_path: str | None = None):
            """
            Export the PlotGroup2D to a PNG file.
            Parameters:
                export_path (str or None): The path to save the PNG file. If None, the file is saved in the current directory with the name of the plot group tag. Defaults to None.
            Warning:
                If the ComsolPostprocessor.export_properties() is not used, the export properties will be the default ones.
            """
            self._api.run()
            file_parent = Path(self.postprocessor.file_path).parent
            if export_path is None: export_path = f"{file_parent}/{self.tag}.png"
            self.postprocessor._export(self.tag, export_path)
        
        def surface(self,
                    tag: str | None = None,
                    expression: str | None = None,
                    unit: str | None = None,
                    dataset: str | None = None,
                    dataset_time: float | str | None = None,
                    color_table: str | None = None,
                    color_table_discrete: int | bool | None = None,
                    color_table_reverse: bool | None = None,
                    color_table_sym: bool | None = None,
                    rangelist: list | bool | None = None,
                    selection: list | str | None = None,
                    ):
            """
            A class to handle the properties of a COMSOL Surface plot.
            Parameters:
                tag (str or None): The tag of the surface plot to edit. If None, a new surface plot is created. Defaults to None.
                expression (str or None): The expression to plot. If None, the expression is not set. Defaults to None.
                unit (str or None): The unit of the expression. If None, the unit is not set. Defaults to None.
                dataset (str or None): The name of the dataset to use for the plot. If None, dataset is not set. Defaults to None.
                dataset_time (float or 'first' or 'last' or None): The time to use for the dataset, needed if dataset is not "parent". If None, time is not set. Defaults to None.
                color_table (str or None): The name of the color table to use for the plot. If None, color table is not set. Defaults to None.
                color_table_discrete (int or False or None): The number of discrete colors to use for the plot. If False, the color table is set as continuous. If None, the color table discretization is not set. Defaults to None.
                color_table_reverse (bool or None): If True, the color table is reversed. If None, the color table reverse setting is not set. Defaults to None.
                color_table_sym (bool or None): If True, the color table is symmetric. If None, the color table symmetry setting is not set. Defaults to None.
                rangelist (list or bool or None): The range of the plot. If False, automatic range is used. If None, color table range is not set. Defaults to None.
                selection (str or list or None): The list of lines to plot. If "all", all lines are plotted. If a Explicit Selection tag is given, it is used. If None, the selection is not set. Defaults to None.
            """
            surface = self.postprocessor._Surface(self, tag, expression, unit, dataset, dataset_time, color_table, color_table_discrete, color_table_reverse, color_table_sym, rangelist, selection)
            return surface


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
            plotgroup = self._PlotGroup2D(self, tag, dataset, label, time, selection, view, showlegends, legendcolor, legendpos, showlegendsmaxmin, showlegendsunit, legendformattingactive, legendnotation, legendprecision)
            return plotgroup
    
    class _Surface:
        def __init__(self,
                    plotgroup: 'ComsolPostprocessor._PlotGroup2D', # | 'ComsolPostprocessor._PlotGroup3D',
                    tag: str | None = None,
                    expression: str | None = None,
                    unit: str | None = None,
                    dataset: str | None = None,
                    dataset_time: float | str | None = None,
                    color_table: str | None = None,
                    color_table_discrete: int | bool | None = None,
                    color_table_reverse: bool | None = None,
                    color_table_sym: bool | None = None,
                    rangelist: list | bool | None = None,
                    selection: list | str | None = None,
                    ):
            """
            A class to handle the properties of a COMSOL Surface plot.
            Parameters:
                plotgroup: The COMSOL PlotGroup2D or PlotGroup3D object from ComsolPostprocessor.
                tag (str or None): The tag of the surface plot to edit. If None, a new surface plot is created. Defaults to None.
                expression (str or None): The expression to plot. If None, the expression is not set. Defaults to None.
                unit (str or None): The unit of the expression. If None, the unit is not set. Defaults to None.
                dataset (str or None): The name of the dataset to use for the plot. If None, dataset is not set. Defaults to None.
                dataset_time (float or 'parent' or None): The time to use for the dataset, needed if dataset is not "parent". If None, time is not set. Defaults to None.
                color_table (str or None): The name of the color table to use for the plot. If None, color table is not set. Defaults to None.
                color_table_discrete (int or False or None): The number of discrete colors to use for the plot. If False, the color table is set as continuous. If None, the color table discretization is not set. Defaults to None.
                color_table_reverse (bool or None): If True, the color table is reversed. If None, the color table reverse setting is not set. Defaults to None.
                color_table_sym (bool or None): If True, the color table is symmetric. If None, the color table symmetry setting is not set. Defaults to None.
                rangelist (list or bool or None): The range of the plot. If False, automatic range is used. If None, color table range is not set. Defaults to None.
                selection (str or list or None): The list of lines to plot. If "all", all lines are plotted. If a Explicit Selection tag is given, it is used. If None, the selection is not set. Defaults to None.
            """
            self.plotgroup = plotgroup
            self.postprocessor = self.plotgroup.postprocessor
            self.model = self.postprocessor.model
            self.expression = expression
            self.unit = unit
            self.dataset = dataset
            self.dataset_time = dataset_time
            self.color_table = color_table
            self.color_table_discrete = color_table_discrete
            self.color_table_reverse = color_table_reverse
            self.color_table_sym = color_table_sym
            self.rangelist = rangelist
            self.selection = selection

            if tag is None:
                    tags = self.plotgroup._api.feature().tags()
                    try :last_tag = max([int(re.findall(r'\d+', str(temptag))[0]) for temptag in tags if re.findall(r'surf\d+', str(temptag))])
                    except: last_tag = 0
                    tag = f'surf{last_tag+1}'
                    self.tag = tag
                    self._api = self.model.result(self.plotgroup.tag).create(self.tag, 'Surface')
                    self.plotgroup.childs.append(self)
                    logger.info(f"Surface {self.tag} created.")
            else:
                self.tag = tag
                self._api = self.model.result(self.plotgroup.tag).feature(self.tag)
                self.plotgroup.childs.append(self)
                logger.info(f"Surface {self.tag} loaded.")
                # NOTE: Load childs
            
            self.apply()

        def apply(self):
            """
            Apply the changes of the Surface to the COMSOL API model.
            """
            if self.expression is not None: self._api.set('expr', self.expression)
            if self.unit is not None: self._api.set('unit', self.unit)
            if self.dataset is not None: self._api.set('data', self.dataset)
            if self.dataset_time is not None: 
                if self.dataset_time == 'parent':
                    self._api.set('solutionparams', 'parent')
                else:
                    self._api.set('t', float(self.dataset_time))
            if self.color_table is not None: self._api.set('colortable', self.color_table)
            if self.color_table_discrete is not None:
                if self.color_table_discrete == False:
                    self._api.set('colortabletype', 'continuous')
                else:
                    self._api.set('colortabletype', 'discrete')
                    self._api.set('bandcount', float(self.color_table_discrete))
            if self.color_table_reverse is not None:
                if self.color_table_reverse: self._api.set('colortablerev', 'on')
                else: self._api.set('colortablerev', 'off')
            if self.color_table_sym is not None:
                if self.color_table_sym: self._api.set('colortablesym', 'on')
                else: self._api.set('colortablesym', 'off')
            if self.rangelist is not None:
                if self.rangelist == False:
                    self._api.set('rangecoloractive', 'off')
                else:
                    self._api.set('rangecoloractive', 'on')
                    self._api.set('rangecolormin', float(self.rangelist[0]))
                    self._api.set('rangecolormax', float(self.rangelist[1]))

            if self.selection is not None:
                sel_tags = self._api.feature().tags()
                try :sel_tag = max([int(re.findall(r'\d+', str(temptag))[0]) for temptag in sel_tags if re.findall(r'sel\d+', str(temptag))])
                except: sel_tag = 0

                if sel_tag == 0:
                    self._api.create('sel1','Selection')
                    sel_tag = 1

                if self.selection == 'all':
                    self._api.feature(f"sel{sel_tag}").selection().all()
                elif isinstance(self.selection, str):
                    self._api.feature(f"sel{sel_tag}").selection().named(self.selection)
                elif isinstance(self.selection, list):                        
                    self._api.feature(f"sel{sel_tag}").selection().set(self.selection)
                else:
                    raise ValueError("Selection must be 'all', a selection tag (str) or a list of integers.")

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

    def edit_surface_plot(self,
                  duplicate: bool,
                  template: str,
                  surface_dict_list: ComsolSurface | list[ComsolSurface],
                  label: str | None = None,                    
                  dataset: str | None = None,
                  time: float | None = None,
                  export: bool = False,
                  export_properties: ComsolExportPlot | None = None,
                  export_path: str | None = None,
                ):
        """
        Plot the results of a COMSOL simulation using a template of a 2D or 3D surface.

        Parameters:
            duplicate (bool): If True, a new plot group is created. If False, the existing plot group is used.
            template (str): The tag of the template to use for the plot.
            label (str or None): The label of the plot group. If None, the label is not set. If duplicate is False, plot group name will not change but label will be used as name of exported file.
            surface_dict_list (ComsolSurface or list of ComsolSurface): A ComsolSurface object or a list of ComsolSurface objects with the properties of the surface plot(s).
            dataset (str or None): The name of the dataset to use for the plot group. If None, the template dataset is used.
            time (float or None): The time step to use for the plot. If None, the template time step is used.
            export (bool): If True, the plot is exported to a file. Defaults to False.
            export_properties (ComsolExportProperties | None): A ComsolExportProperties object with the properties of the export. If None, the default properties are used.
            export_path (str or None): The path to the folder to save the exported plot. If None, the default path is used.
        """

        tags = self.model.result().tags()
        last_tag = max([int(re.findall(r'\d+', str(tag))[0]) for tag in tags if re.findall(r'\d+', str(tag))])

        original_pg = self.model.result(template)
        if duplicate:
            plot_group = self.model.result().duplicate(f'pg{last_tag+1}', template)
        else:
            plot_group = original_pg

        if label is not None: plot_group.label(label)
        if isinstance(surface_dict_list, list):
            N_surfaces = len(surface_dict_list)
        else:
            N_surfaces = 1
            surface_dict_list = [surface_dict_list]

        def config_surface(surface, surface_dict, plot_group):
            if surface_dict.dataset is not None: surface.set('data', surface_dict.dataset)
            if surface_dict.dataset_time is not None: surface.set('t', float(surface_dict.dataset_time))
            surface.set('expr', surface_dict.expression)
            if surface_dict.unit is not None: surface.set('unit', surface_dict.unit)

            if surface_dict.color_table is not None: surface.set('colortable', surface_dict.color_table)
            if surface_dict.color_table_discrete is False: surface.set('colortabletype', 'continuous')
            if surface_dict.color_table_discrete:
                surface.set('colortabletype', 'discrete')
                surface.set('bandcount', float(surface_dict.color_table_discrete))
            if surface_dict.color_table_reverse: surface.set('colortablerev', 'on')
            if not surface_dict.color_table_reverse: surface.set('colortablerev', 'off')
            if surface_dict.color_table_sym: surface.set('colortablesym', 'on')
            if not surface_dict.color_table_sym: surface.set('colortablesym', 'off')

            if surface_dict.rangelist is not None:
                surface.set('rangecoloractive', 'on')
                surface.set('rangecolormin', float(surface_dict.rangelist[0]))
                surface.set('rangecolormax', float(surface_dict.rangelist[1]))
            else: surface.set('rangecoloractive', 'off')

            if surface_dict.selection is not None:
                try:
                    surface.feature('sel1')
                except:
                    surface.create('sel1', 'Selection')
                if isinstance(surface_dict.selection, str):
                    if surface_dict.selection == 'all':
                        surface.feature('sel1').active(False)
                    else:
                        surface.feature('sel1').selection().named(surface_dict.selection)
                else:
                    JIntArray = jpype.JArray(jpype.JInt)
                    intlist = JIntArray(surface_dict.selection)
                    surface.feature('sel1').selection().set(intlist)

            if dataset is not None: plot_group.set('data', dataset)
            if time is not None: plot_group.set('t', float(time))

        if N_surfaces == 1:
            surface_dict = surface_dict_list[0]
            surface = plot_group.feature(plot_group.feature().tags()[0])
            config_surface(surface, surface_dict, plot_group)

        elif N_surfaces > 1:
            if dataset is not None: plot_group.set('data', dataset)
            if time is not None: plot_group.set('t', float(time))

            for i in range(N_surfaces):
                surface_dict = surface_dict_list[i]
                surface = plot_group.feature(plot_group.feature().tags()[i])
                config_surface(surface, surface_dict, plot_group)

        plot_group.run()

        if export:
            # Check if 'img1' already exists, if so, remove it before creating
            export_tags = self.model.result().export().tags()
            if 'img1' in export_tags:
                image_export = self.model.result().export().remove('img1')
            image_export = self.model.result().export().create('img1', 'Image')

            image_export.set('plotgroup', f'pg{last_tag+1}')
            if label is None:
                raise ValueError("If exporting, label must be set to name the exported file.")
            logger.info(f"Exporting image pg{last_tag+1}_{label}.png")
            if export_path is None:
                image_export.set('pngfilename', f'pg{last_tag+1}_{label}.png')
            else:
                image_export.set('pngfilename', f'{export_path}/pg{last_tag+1}_{label}.png')
            if export_properties is not None:
                image_export.set('resolution', float(export_properties.resolution))
                image_export.set('unit', 'px')
                image_export.set('size','manualweb')
                image_export.set('width', float(export_properties.width))
                image_export.set('height', float(export_properties.height))
                image_export.set('fontsize', float(export_properties.font_size))
            image_export.run()
        
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

    def export_image(self,
                     plotgroup_tag: str,
                     export_path: str,
                     export_properties: _ExportProperties | None = None,):
        """
        Export a plot group to an image file.
        Parameters:
            plotgroup_tag (str): The tag of the plot group to export.
            export_path (str): The path to the folder to save the exported plot.
            export_properties (_ExportProperties | None): A _ExportProperties object with the properties of the export. If None, the default properties are used.
        """
        # Check if 'img1' already exists, if so, remove it before creating
        export_tags = self.model.result().export().tags()
        if 'img1' in export_tags:
            image_export = self.model.result().export().remove('img1')
        image_export = self.model.result().export().create('img1', 'Image')

        image_export.set('plotgroup', plotgroup_tag)        
        logger.info(f"Exporting image {export_path}")
        
        if export_properties is not None:
            image_export.set('resolution', float(export_properties.resolution))
            image_export.set('unit', 'px')
            image_export.set('size','manualweb')
            image_export.set('width', float(export_properties.width))
            image_export.set('height', float(export_properties.height))
            image_export.set('fontsize', float(export_properties.font_size))
        image_export.run()
