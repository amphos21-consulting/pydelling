from pydelling.postprocessing.comsol_postprocessor import ComsolPostprocessor

# First, initialize the ComsolPostprocessor with the desired COMSOL version and open the file
comsol = ComsolPostprocessor(file_path=r"test.mph", version='6.2')

# This function edits an existing or creates a new Table in the COMSOL file.

# Some Table properites can be modified with the parameters of the function. See pydelling documentation to find all possible parameters. Others needs to be accessed with the functions of the Table class. For direct acces to API, use ._api attribute of the Table objects.

# After any change, the apply() method must be called to apply the changes to the COMSOL file.

table = comsol.table(tag='tbl1', columnheaders=["Temps (d)","P1", "P2", "P3", "P4", "P5", "P6"])

row = [1]*len(table.get_columnheaders())
table.addRows(row)

table.removeRow(4)

df = table.get_table()

table2 = table.duplicate()
table2.clear()

table.export()
table3 = comsol.table()
table3.import_table('tbl1.csv')
table3.get_table()

# Finally, the COMSOL file can be saved with the changes. If no path is given, it will overwrite the original file.
comsol.save("test_tables.mph")

# This function apply the changes to all the objects that have been initialized in the ComsolPostprocessor instance.
comsol.apply()
