import re
import logging
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_postprocessor import ComsolPostprocessor
    from .comsol_table import _Table

class _DerivedValue:
    #!BUG: @miquel.iglesia: No he encontrado el modo de crear nuevos Derived Values o cambiar sus propiedades
    #!NOTE: Si que es pot!
    def __init__(self,
                    postprocessor: 'ComsolPostprocessor',
                    tag: str,
                    table_tag: str | None = None,
                    ):
        """
        A class to handle the properties of a COMSOL Derived Value.
        Parameters:
            postprocessor: The COMSOL Postprocessor object from ComsolPostprocessor.
            tag (str): The tag of the derived value.
            table_tag (str | None): The tag of the table to export the results to. If 'new', a new table is created. If None, the table assosciated with this derived value will be used. If its not associated to any table a new one will be created. Defaults to None.
        """
        self.postprocessor = postprocessor
        self.model = self.postprocessor.model
        self.tag = tag
        self.table_tag = table_tag
        self.childs = []

        self.tag = tag
        self._api = self.model.result().numerical(self.tag)
        self.postprocessor.childs.append(self)
        logger.info(f"Derived value {self.tag} loaded.")

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
        self.table = self.childs[0]
            
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
                export_path: str | None = None,
                ifexists: str = "overwrite"):
        """
        Export the table of the Derived Value to a TXT/CSV/DAT file.
        Parameters:
            export_path (str or None): The path to save the TXT/CSV/DAT file. If None, the file is saved in the current directory with the name of the table tag as CSV. Defaults to None.
            ifexists (str): What to do if the export file already exists. Options are 'overwrite' and 'append'. Defaults to 'overwrite'.
        """
        self.table.export(export_path,ifexists)
    
