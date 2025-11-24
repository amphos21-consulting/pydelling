import re
import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_plotgroup1D import _PlotGroup1D
    
class _LineGraph:
    """
    A class to handle the properties of a COMSOL Line Graph.
    """
    def __init__(self,
                    plotgroup: '_PlotGroup1D',
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
            if self.tag not in self.plotgroup.get_childs():
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
