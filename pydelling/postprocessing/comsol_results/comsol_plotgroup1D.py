import re
import logging
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_postprocessor import ComsolPostprocessor

from .comsol_plots.comsol_linegraph import _LineGraph
from .comsol_plots.comsol_pointgraph import _PointGraph
     
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
            try: last_tag = max([int(re.findall(r'\d+', str(temptag))[0]) for temptag in tags if re.findall(r'\d+', str(temptag))])
            except: last_tag = 0
            tag = f'pg{last_tag+1}'
            self.tag = tag
            self._api = self.model.result().create(self.tag, 'PlotGroup1D')
            self.postprocessor.childs.append(self)
            logger.info(f"1D Plot Group {self.tag} created.")
        else:
            
            self.tag = tag
            self._api = self.model.result(self.tag)
            if self.tag not in self.postprocessor.get_childs():
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

    def get_childs(self):
        """
        Get the tags of the loaded childs of the PlotGroup1D
        """
        tags = []
        for child in self.childs:
            tags.append(child.tag)
        return tags

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
        linegraph = _LineGraph(self, tag, expression, unit, dataset, dataset_param, dataset_time, selection, xdata, xdataexpr, xdataunit, linecolor, colorcycle, linestyle, linewidth, marker, plotonsecyaxis, legend, legendmethod, legendmanuallist, legendprefix, legendsuffix, legendpattern, legendexprprecision)
        return linegraph
                
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
        pointgraph = _PointGraph(self, tag, expression, unit, dataset, dataset_param, dataset_time, selection, xdata, xdataexpr, xdataunit, linecolor, colorcycle, linestyle, linewidth, marker, plotonsecyaxis, legend, legendmethod, legendmanuallist, legendprefix, legendsuffix, legendpattern, legendexprprecision)
        return pointgraph
