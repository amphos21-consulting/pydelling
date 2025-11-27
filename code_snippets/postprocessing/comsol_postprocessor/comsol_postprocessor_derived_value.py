from pydelling.postprocessing.comsol_postprocessor import ComsolPostprocessor

# First, initialize the ComsolPostprocessor with the desired COMSOL version and open the file
comsol = ComsolPostprocessor(file_path=r"test.mph", version='6.2')

# This function edits and manages a derived value evaluation defined in the COMSOL file.

# The derived value properites can be modified with the parameters of the function. See pydelling documentation to find all possible parameters. For direct acces to API, use ._api attribute of the DerivedValue or Table objects.

# The DerivedValue objects only have one child, which is its table. Its properties can be modified by accessing the childs attribute of the DerivedValue object or directly by DirectValue.table.

# After any change, the apply() method must be called to apply the changes to the COMSOL file.
derived_value = comsol.derived_value('pev1')
derived_value.expression = ['dl.H']
derived_value.description = ['Head']
derived_value.apply()

# The derived_value has to be run using run(), that will remove the old data in the table, or with run_append() which will append the results in a new column.
derived_value.run()
derived_value.expression = ['p']
derived_value.unit = ['kPa']
derived_value.run_append()

# And results can be cleared
derived_value.table.clear()

# Results can be accessed via the DerivedValue object or directly via the Table object
# get_result returns a pandas DataFrame
df = derived_value.get_result()
# or equivalently
df2 = derived_value.table.get_table()

# And they can also be exported
derived_value.export(header=True)
derived_value.table.export(header=None)

# New derived values can be created duplicating and existing one.
dev2 = derived_value.duplicate()
dev2.expression = ['p', 'dl.U']
dev2.unit = ['kPa', 'm/s']
dev2.apply()
dev2.run()
df2 = dev2.get_result()

# Or created from scratch. Then, the derived value type must be defined: "EvalPoint", "EvalGlobal", "AvLine", "AvSurface", "AvVolume", "IntLine", "IntSurface", "IntVolume", "MinLine", "MinSurface", "MinVolume, "MaxLine", "MaxSurface" or "MaxVolume".
dev2 = comsol.derived_value(dev_type="AvSurface", 
                            table_tag="new",
                            expression=['p','dl.U'],
                            description=['Pressure', 'Velocity'],
                            dataset='dset1',
                            label="ComsolPostprocessor Average",
                            time="all",
                            selection='all',
                            )
dev2.run()
dev2.export()

# Finally, the COMSOL file can be saved with the changes. If no path is given, it will overwrite the original file.
comsol.save("test_derived_values.mph")

# This function apply the changes to all the objects that have been initialized in the ComsolPostprocessor instance.
comsol.apply()
