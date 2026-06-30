import re
import logging
from pathlib import Path
from typing import TYPE_CHECKING
import os

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_results import ComsolResults

from .comsol_plots_objects.comsol_surface import _Surface    

class _PlotGroup2D:
    """Wrapper around a COMSOL 2D plot group.

    Category: COMSOL management.
    Tags: comsol, results, plot-group, 2d, surface.
    Use when: to create or modify 2D COMSOL result plot
        groups and surface plot children.
    """

    def __init__(self,
                    results: 'ComsolResults',
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
            results: The COMSOL results object from ComsolManager.
            tag (str or None): The tag of the plot group to edit. If None, a new plot group is created. Defaults to None.
            dataset (str or None): The name of the dataset to use for the plot group. If None, the dataset is not set. Defaults to None.
            label (str or None): The label of the plot group. If None, the label is not set. Defaults to None.
            time (float or str or None): The time step to use for the plot group or "first" or "last". If None, the time is not set. Defaults to None.
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
        self.results = results
        self.comsol = self.results.comsol
        self.manager = self.comsol.manager
        self.model = self.results.model
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
            try: last_tag = max([int(re.findall(r'\d+', str(temptag))[0]) for temptag in tags if re.findall(r'\d+', str(temptag))])
            except: last_tag = 0
            tag = f'pg{last_tag+1}'
            self.tag = tag
            self._api = self.model.result().create(self.tag, 'PlotGroup2D')
            self.results.childs.append(self)
            logger.info(f"2D Plot Group {self.tag} created.")
        else:
            self.tag = tag
            self._api = self.model.result(self.tag)
            if self.tag not in self.results.get_childs():
                self.results.childs.append(self)
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
                if self.time == 'first':
                    self._api.set('looplevel', self.manager.__java_int__(1))
                elif self.time == 'last':
                    dset_tag = self._api.getString('data')
                    sol_tag = self.model.result().dataset(dset_tag).getString('solution')
                    timesteps = list(self.model.sol(sol_tag).getSize())[1]
                    self._api.set('looplevel',timesteps)
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
        if self.legendprecision is not None: self._api.set('legendprecision', self.manager.__java_int__(self.legendprecision))



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
        plot_group = self.results.plot_group_2D(tag=f'pg{last_tag+1}')
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
        if export_path is None:
            parent = os.getcwd()
            export_path = f"{parent}/{self.tag}.png"
        self.results._export(self.tag, export_path)
    
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
            dataset_time (float or 'parent' or None): The time to use for the dataset or "first" or "last" or "parent", needed if dataset is not "parent". If None, time is not set. Defaults to None.
            color_table (str or None): The name of the color table to use for the plot. If None, color table is not set. Defaults to None.
            color_table_discrete (int or False or None): The number of discrete colors to use for the plot. If False, the color table is set as continuous. If None, the color table discretization is not set. Defaults to None.
            color_table_reverse (bool or None): If True, the color table is reversed. If None, the color table reverse setting is not set. Defaults to None.
            color_table_sym (bool or None): If True, the color table is symmetric. If None, the color table symmetry setting is not set. Defaults to None.
            rangelist (list or bool or None): The range of the plot. If False, automatic range is used. If None, color table range is not set. Defaults to None.
            selection (str or list or None): The list of lines to plot. If "all", all lines are plotted. If a Explicit Selection tag is given, it is used. If None, the selection is not set. Defaults to None.
        """
        surface = _Surface(self, tag, expression, unit, dataset, dataset_time, color_table, color_table_discrete, color_table_reverse, color_table_sym, rangelist, selection)
        return surface

    def get_childs(self):
        """
        Get the tags of the loaded childs of the PlotGroup2D
        """
        tags = []
        for child in self.childs:
            tags.append(child.tag)
        return tags
