from pydelling.postprocessing.comsol_postprocessor import ComsolPostprocessor

# First, initialize the ComsolPostprocessor with the desired COMSOL version and open the file
comsol = ComsolPostprocessor(file_path=r"test.mph", version='6.2')

# This function edits an existing line graph in the COMSOL file or creates a new one duplicating the given line graph as a template.
# The plot group properites can be modified with the parameters of the function. But the line graph properties need to be defined with ComsolLine objects.

# If the plot group has more than one line graph, all lines can be modified, providing a list of ComsolLine objects with the same length as the number of lines.

# ComsolLine has lots of parameters to define the line graph properties. There is no need to define all parameters, ONLY THE ONES WE WANT TO CHANGE.

line1 = comsol.ComsolLine(
    dataset = 'cln1',
    expression = 'p',
    unit = 'kPa',
    xdata = 'expr',
    xdataexpr = 'z',
    xdataunit = 'mm',
    dataset_param="parent"
)

line2 = comsol.ComsolLine(
    dataset = 'cln1',
    expression = 'dl.U',
    unit = 'm/s',
    xdata = 'expr',
    xdataexpr = 'z',
    xdataunit = 'mm',
    dataset_param="parent",
    linecolor="cyclereset"
)

export = comsol.ComsolExportPlot(
    resolution = 96,
    width = 800,
    height = 600,
    font_size = 15,
)

# 'pg7' plot group will be duplicated. This plot group has two line graphs, and the plot will be exported in a png file.
comsol.edit_line_graph(True,'pg7', [line1, line2], label="Line_Mix", time=[1,3,5], export=True, export_properties=export)

# This new plot group will not be saved in the COMSOL file. If we want to save it, we need to use the ComsolPostprocessor.save() function.
