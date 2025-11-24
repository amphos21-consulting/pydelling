import pandas as pd
import re
import logging
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_postprocessor import ComsolPostprocessor
from jpype import JArray, JDouble, JString


class _Table:
    def __init__(self,
                    postprocessor: 'ComsolPostprocessor',
                    tag: list | None = None,
                    columnheaders: list | None = None,
                    derived_value: None = None
                    ):
        """
        A class to handle the properties of a COMSOL Table.
        Parameters:
            postprocessor: The COMSOL Postprocessor object from ComsolPostprocessor.
            tag (str or None): The tag of the table. If None, a new table is created. Defaults to None.
            columnheaders (list of str or None): A list with the headers of the columns. List lenght must be the same as the number of columns. If None, the column headers are not set. Defaults to None.
            derived_value (_DerivedValue or None): The derived value that writes the table. If None, the derived_value is not set. Defaults to None.
        """
        self.postprocessor = postprocessor
        self.model = self.postprocessor.model
        self.columnheaders = columnheaders
        self.derived_value = derived_value

        if tag is None:
            tags = self.model.result().table().tags()
            last_tag = max([int(re.findall(r'\d+', str(tag))[0]) for tag in tags if str(tag).startswith('tbl') and re.findall(r'\d+', str(tag))])
            tag = f'tbl{last_tag+1}'
            self.tag = tag
            self._api = self.model.result().table().create(self.tag, 'Table')
            self.postprocessor.childs.append(self)
            logger.info(f"Table {self.tag} created.")
        else:
            self.tag = tag
            self._api = self.model.result().table(self.tag)
            if self.tag not in self.postprocessor.get_childs():
                self.postprocessor.childs.append(self)
            logger.info(f"Table {self.tag} loaded.")

        self.apply()

    def apply(self):
        """
        Apply the changes of the Table to the COMSOL API model.
        """
        if self.columnheaders is not None: self._api.setColumnHeaders(self.columnheaders)
        
    def get_columnheaders(self):
        """
        Returns the column headers of the Table.
        """
        headers_java = self._api.getColumnHeaders()
        headers = []
        for i in headers_java:
            headers.append(str(i))
        return headers
    
    def get_nrows(self):
        """
        Returns the number of rows
        """
        return self._api.getNRows()
    
    def add_columns(self,
                   headers: list | str,
                   data: list):
        """
        Warning: addColumns() is not implemented
        Adds one or more columns to the Table.
        Parameters:
            headers (list of str or str): The headers of the new columns.
            data (list of lists of float or list of float): The data of the new columns.
        """
        #!BUG: com.comsol.util.exceptions.FlException: Exception: com.comsol.util.exceptions.FlException: Number of rows does not match table size Messages: Number of rows does not match table size.

        # if not isinstance(headers, list):
        #     headers = [headers]
        #     data = [data]
        
        # DoubleArray = JArray(JDouble)
        # DoubleArray2D = JArray(DoubleArray)

        # data_java = DoubleArray2D(len(data))
        # for i, row in enumerate(data):
        #     data_java[i] = DoubleArray(row)
        
        # header_java = JArray(JString)([self.postprocessor.__java_str__(x) for x in headers])

        # self._api.addColumns(header_java, data_java)
        logger.warning("addColumns() is not implemented")
        pass

    def add_rows(self,
                data: list):
        """
        Adds one or more rows to the Table.
        Parameters:
            data (list of lists of float or list of float): The data of the new rows.
        """
        if isinstance(data[0],list):
            self._api.addRows(data)
        else: self._api.addRow(data)

    def remove_row(self,
                   index: int):
        """
        Removes a row of the Table.
        """
        self._api.removeRow(index)

    def get_table(self):
        """
        Returns a DataFrame with the table data
        """
        t_java = self._api.getTableData(True)
        t = []
        for i in range(len(t_java)):
            col = []
            for j in range(len(t_java[i])):
                col.append(float(str(t_java[i][j])))
            t.append(col)
        df = pd.DataFrame(t, columns=self.get_columnheaders())
        return df

    def clear(self):
        """
        Removes all Table data and column headers.
        """
        logger.info(f"Table {self.tag} cleared.")
        self._api.clearTableData()
    
    def duplicate(self):
        """
        Duplicate the Table. 
        Returns:
            A Table object.
        """
        tags = self.model.result().table().tags()
        last_tag = max([int(re.findall(r'\d+', str(tag))[0]) for tag in tags if str(tag).startswith('tbl') and re.findall(r'\d+', str(tag))])
        logger.info(f"Duplicating Table {self.tag} to tbl{last_tag+1}...")
        self.model.result().table().duplicate(f'tbl{last_tag+1}', self.tag)
        table = self.postprocessor.table(tag=f'tbl{last_tag+1}')
        return table

    def export(self,
                export_path: str | None = None,
                ifexists: str = "overwrite"):
        """
        Export the Table to a TXT/CSV/DAT file.
        Parameters:
            export_path (str or None): The path to save the TXT/CSV/DAT file. If None, the file is saved in the current directory with the name of the table tag as CSV. Defaults to None.
            ifexists (str): What to do if the export file already exists. Options are 'overwrite' and 'append'. Defaults to 'overwrite'.
        """
        if export_path is None:
            file_parent = Path(self.postprocessor.file_path).parent
            export_path = f"{file_parent}/{self.tag}.csv"
        logger.info(f"Exporting Table {self.tag} to {export_path}")
        export_list = self.model.result().export().tags()
        if 'tbl1' in export_list:
            export_tbl = self.model.result().export('tbl1')
        else:
            export_tbl = self.model.result().export().create('tbl1', 'Table')

        export_tbl.set('header', False)
        export_tbl.set('table', self.tag)
        export_tbl.set('ifexists', ifexists)
        export_tbl.set('filename', export_path)
        export_tbl.run()

    def import_table(self,
               import_path: str,
               delim: str | None = None):
        """
        Import a table from a local TXT/CSV/DAT file into the COMSOL Table
        Warning: old data will be overwriten
        Parameters:
            import_path (str): The path of the table to import
            delim (str or None): The delimiter used in the file. If None, delimiter will not be specified. Defaults to None.
        """
        self.clear()
        if delim is None: self._api.loadFile(import_path)
        else: self._api.loadFile(import_path, delim)
        logger.info(f"{import_path} imported into {self.tag}")
  