from pydelling.postprocessing.comsol_postprocessor import ComsolPostprocessor

# First, initialize the ComsolPostprocessor with the desired COMSOL version and open the file
comsol = ComsolPostprocessor(file_path=r"test.mph", version='6.2')

# This function runs a derived value evaluation defined in the COMSOL file.
# This derived value can be a point evaluation, a surface integration, a line integration, etc.

dev_tag = 'pev1'
table = 'tbl1'

# The derived value data could be exported to a csv file if file_name is provided
comsol.run_derived_value(dev_tag, table)
