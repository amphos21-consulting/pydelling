from pydelling.postprocessing.comsol_postprocessor import ComsolPostprocessor

# First, initialize the ComsolPostprocessor with the desired COMSOL version and open the file
comsol = ComsolPostprocessor(file_path=r"test.mph", version='6.2')

# This function edits an existing surface plot in the COMSOL file or creates a new one duplicating the given surface plot as a template.
# The plot group properites can be modified with the parameters of the function. But the surface plot properties need to be defined with ComsolSurface objects.

# If the plot group has more than one surface plot, all surface can be modified, providing a list of ComsolSurface objects with the same length as the number of surface plots.

# ComsolSurface has lots of parameters to define the surface plot properties. There is no need to define all parameters, ONLY THE ONES WE WANT TO CHANGE.

surface1 = comsol.ComsolSurface(
    dataset = 'parent',
    expression = 'p',
    unit = 'kPa',
    color_table = 'Rainbow',
    color_table_discrete = 10,
    color_table_reverse = False,
    color_table_sym = False,
    rangelist = None,
    selection = False,
)

surface2 = comsol.ComsolSurface(
    dataset = 'parent',
    expression = 'dl.U',
    unit = 'm/s',
    color_table = 'Dipole',
    color_table_discrete = 10,
    color_table_reverse = False,
    color_table_sym = False,
    rangelist = None,
    selection = [2],
)

export = comsol.ComsolExportPlot(
    resolution = 96,
    width = 1500,
    height = 1000,
    font_size = 15,
)

# 'pg4' plot group will be duplicated. This plot group has two surface plots, and the plot will be exported in a png file.
comsol.edit_surface_plot(True,'pg4', [surface1, surface2], label="Mix", dataset='dset1', time=5, export=True, export_properties=export)

# This new plot group will not be saved in the COMSOL file. If we want to save it, we need to use the ComsolPostprocessor.save() function.
