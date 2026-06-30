import re
import logging
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_plotgroup2D import _PlotGroup2D

class _Surface:
    """Wrapper around a COMSOL surface plot.

    Category: COMSOL management.
    Tags: comsol, results, surface-plot, 2d.
    Use when: an MCP agent needs to configure surface expressions, color tables,
        ranges, selections, or datasets under a 2D plot group.
    """

    def __init__(self,
                plotgroup: '_PlotGroup2D', # | 'ComsolPostprocessor._PlotGroup3D',
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
            plotgroup: The COMSOL PlotGroup2D or PlotGroup3D object from ComsolManager.
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
        self.plotgroup = plotgroup
        self.results = self.plotgroup.results
        self.comsol = self.results.comsol
        self.manager = self.comsol.manager
        self.model = self.results.model
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
            if self.tag not in self.plotgroup.get_childs():
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
            elif self.dataset_time == 'first':
                self._api.set('looplevel', 1)
            elif self.dataset_time == 'last':
                dset_tag = self._api.getString('data')
                sol_tag = self.model.result().dataset(dset_tag).getString('solution')
                timesteps = list(self.model.sol(sol_tag).getSize())[1]
                self._api.set('looplevel',timesteps)
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
