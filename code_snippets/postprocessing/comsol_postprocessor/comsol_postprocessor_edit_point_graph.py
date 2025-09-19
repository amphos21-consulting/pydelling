from pydelling.postprocessing.comsol_postprocessor import ComsolPostprocessor

# First, initialize the ComsolPostprocessor with the desired COMSOL version and open the file
comsol = ComsolPostprocessor(file_path=r"test.mph", version='6.2')

# This function edits an existing point graph in the COMSOL file or creates a new one duplicating the given point graph as a template.
# The plot group properites can be modified with the parameters of the function. But the point graph properties need to be defined with ComsolPoint objects.

# If the plot group has more than one point graph, all points can be modified, providing a list of ComsolLine objects with the same length as the number of points.

# ComsolLine has lots of parameters to define the point graph properties. There is no need to define all parameters, ONLY THE ONES WE WANT TO CHANGE.

line1 = comsol.ComsolLine(
    dataset = 'parent',
    expression = 'p',
    unit = 'kPa',
    xdata = 'expr',
    xdataexpr = 't',
    xdataunit = 'd',
    dataset_param="parent",
    marker="cycle",
    selection=[7,4,10],
    linestyle='none',
)

export = comsol.ComsolExportPlot(
    resolution = 96,
    width = 800,
    height = 600,
    font_size = 15,
)
comsol.edit_point_graph(True,'pg6', line1, label="Evolution", time="all", export=True, export_properties=export)

# This new plot group will not be saved in the COMSOL file. If we want to save it, we need to use the ComsolPostprocessor.save() function.
