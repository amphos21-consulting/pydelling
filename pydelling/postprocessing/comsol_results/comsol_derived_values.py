import re
import logging
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_postprocessor import ComsolPostprocessor
    from .comsol_table import _Table

class _DerivedValue:
    def __init__(self,
                    postprocessor: 'ComsolPostprocessor',
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
            postprocessor: The COMSOL Postprocessor object from ComsolPostprocessor.
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
        self.postprocessor = postprocessor
        self.model = self.postprocessor.model
        self.tag = tag
        self.dev_tpye = dev_type
        if self.tag is None and self.dev_tpye is None:
            logger.error("Either tag or dev_type must be defined.")
        self.table_tag = table_tag
        self.expression = expression
        self.unit = unit
        self.description = description
        self.dataset = dataset
        self.label = label
        self.time = time
        self.selection = selection
        self.method = method
        self.integration_order = integration_order
        self.consider2Daxi = consider2Daxi
        self.normalization = normalization
        self.transformation = transformation
        self.transform_method = transform_method
        self.transform_cumulative = transform_cumulative
        self.childs = []

        if tag is None:
            tags = self.model.result().numerical().tags()
            if self.dev_tpye == "EvalPoint": self.type_tag = "pev"
            elif self.dev_tpye == "EvalGlobal": self.type_tag = "gev"
            elif self.dev_tpye == "AvLine" or self.dev_tpye == "AvSurface" or self.dev_tpye == "AvVolume": self.type_tag = "av"
            elif self.dev_tpye == "IntLine" or self.dev_tpye == "IntSurface" or self.dev_tpye == "IntVolume": self.type_tag = "int"
            elif self.dev_tpye == "MinLine" or self.dev_tpye == "MinSurface" or self.dev_tpye == "MinVolume": self.type_tag = "min"
            elif self.dev_tpye == "MaxLine" or self.dev_tpye == "MaxSurface" or self.dev_tpye == "MaxVolume": self.type_tag = "max"
            else: logger.error(f'dev_tpye {self.dev_tpye} is not valid. Valid values are "EvalPoint", "EvalGlobal", "AvLine", "AvSurface", "AvVolume", "IntLine", "IntSurface", "IntVolume", "MinLine", "MinSurface", "MinVolume, "MaxLine", "MaxSurface" and "MaxVolume".')
            try: last_tag = last_tag = max([int(re.findall(r'\d+', str(tag))[0]) for tag in tags if str(tag).startswith(self.type_tag) and re.findall(r'\d+', str(tag))])
            except: last_tag = 0
            tag = f'{self.type_tag}{last_tag+1}'
            self.tag = tag
            self._api = self.model.result().numerical().create(self.tag, self.dev_tpye)
            self.postprocessor.childs.append(self)
            logger.info(f"Derived Value {self.tag} created.")
        else:
            self.tag = tag
            self._api = self.model.result().numerical(self.tag)
            if self.tag not in self.postprocessor.get_childs():
                self.postprocessor.childs.append(self)
            logger.info(f"Derived value {self.tag} loaded.")
            self.dev_tpye = self._api.getType()
            m = re.match(r'^(.*?)(\d+)$', str(self.tag))
            self.type_tag = m.group(1)       

        self.apply()

    def apply(self):
        """
        Apply the changes of the DerivedValue to the COMSOL API model.
        """
        self.childs = []
        if self.table_tag is None:
            self.table_tag = self.model.result().numerical(self.tag).getString('table')
        if self.table_tag is not None:
            if self.table_tag == "new" or self.table_tag == "New":
                self.childs.append(self.postprocessor.table(derived_value=self))
                self.table_tag = self.childs[0].tag
            else:
                self.childs.append(self.postprocessor.table(self.table_tag, derived_value=self))
            self._api.set('table',self.table_tag)
        self.table = self.childs[0]

        if self.expression is not None: self._api.set('expr', self.expression)
        if self.unit is not None: self._api.set('unit', self.unit)
        if self.description is not None: self._api.set('descr', self.description)
        if self.dataset is not None: self._api.set('data', self.dataset)

        if self.label is not None: self._api.label(self.label)
        if self.time is not None:
                if self.time == 'all':
                    self._api.set('innerinput', 'all')
                elif self.time == 'first':
                    self._api.set('innerinput', 'first')
                elif self.time == 'last':
                    self._api.set('innerinput', 'last')
                else:
                    self._api.set('innerinput', 'interp')
                    self._api.set('t', self.time)

        if self.selection is not None:
            if self.selection == 'all':
                self._api.selection().all()
            elif isinstance(self.selection, str):
                self._api.selection().named(self.selection)
            elif isinstance(self.selection, list):                        
                self._api.selection().set(self.selection)
            else:
                raise ValueError("Selection must be 'all', a selection tag (str) or a list of integers.")
            
        if self.method is not None: self._api.set('method', self.method)
        if self.integration_order is not None:
            if self.integration_order == 'auto':
                self._api.set('intorderactive','on')
            else:
                self._api.set('intorderactive', 'off')
                self._api.set('intorder', self.integration_order)
        if self.consider2Daxi:
            if self.dev_tpye in ["AvLine", "IntLine"]:
                self._api.set('intsurface', 'on')
            elif self.dev_tpye in ["AvSurface", "IntSurface"]:
                self._api.set('intvolume', 'on')
            else: logger.warning("consider2Daxi is only used in AvLine, AvSurface, IntLine and IntSurface. Otherwise, it does not have any effect.")
        if self.consider2Daxi is False:
            if self.dev_tpye in ["AvLine", "IntLine"]:
                self._api.set('intsurface', 'off')
            elif self.dev_tpye in ["AvSurface", "IntSurface"]:
                self._api.set('intvolume', 'off')
            else: logger.warning("consider2Daxi is only used in AvLine, AvSurface, IntLine and IntSurface. Otherwise, it does not have any effect.")
        if self.normalization is not None: self._api.set("normalization", self.normalization)
        if self.transformation is not None: self._api.set("dataseries", self.transformation)
        if self.transform_method is not None: self._api.set("dataseriesmethod", self.transform_method)
        if self.transform_cumulative is not None: self._api.set("dataseriescumulative", self.transform_cumulative)

            
    def run(self):
        """
        Run the DerivedValue and overwrite its associeted Table.
        """
        self.table.clear()
        logger.info(f"Running Dervied Value {self.tag}...")
        self._api.setResult()
        logger.info(f"Dervied Value {self.tag} run completed.")
    
    def run_append(self):
        """
         Run the DerivedValue and overwrite its associeted Table.
        """
        logger.info(f"Running Dervied Value {self.tag}...")
        self._api.appendResult()
        logger.info(f"Dervied Value {self.tag} run completed.")

    def get_result(self):
        """
        Returns a DataFrame with the table of the Derived Value.
        Warning: This function does not run the Derived Value. It must be run with run() or run_append()
        """
        df = self.table.get_table()
        return df

    def duplicate(self):
        """
        Duplicate the Derived Value. 
        Returns:
            A Derived Value object.
        """
        tags = self.model.result().numerical().tags()
        last_tag = last_tag = max([int(re.findall(r'\d+', str(tag))[0]) for tag in tags if str(tag).startswith(self.type_tag) and re.findall(r'\d+', str(tag))])
        logger.info(f"Duplicating Derived Value {self.tag} to {self.type_tag}{last_tag+1}...")
        self.model.result().numerical().duplicate(f'{self.type_tag}{last_tag+1}', self.tag)
        derived_value = self.postprocessor.derived_value(tag=f'{self.type_tag}{last_tag+1}', table_tag='new')
        return derived_value

    def export(self,
                export_path: str | None = None,
                header: bool | None = None,
                ifexists: str = "overwrite"):
        """
        Export the table of the Derived Value to a TXT/CSV/DAT file.
        Parameters:
            export_path (str or None): The path to save the TXT/CSV/DAT file. If None, the file is saved in the current directory with the name of the derived value tag as CSV. Defaults to None.
            header (bool or None): Include header in the file. If None, the header is not set. Defaults to None.
            ifexists (str): What to do if the export file already exists. Options are 'overwrite' and 'append'. Defaults to 'overwrite'.
        """
        if export_path is None:
            file_parent = Path(self.postprocessor.file_path).parent
            export_path = f"{file_parent}/{self.tag}.csv"
        self.table.export(export_path,header,ifexists)
    
