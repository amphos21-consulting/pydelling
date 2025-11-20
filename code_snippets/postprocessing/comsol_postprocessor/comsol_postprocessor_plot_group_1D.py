from pydelling.postprocessing.comsol_postprocessor import ComsolPostprocessor

# First, initialize the ComsolPostprocessor with the desired COMSOL version and open the file
comsol = ComsolPostprocessor(file_path=r"test.mph", version='6.2')

# This function edits an existing or creates a new 1D plot group in the COMSOL file.

# The plot group properites can be modified with the parameters of the function. See pydelling documentation to find all possible parameters. For direct acces to API, use ._api attribute of the PlotGroup1D, LineGraph or PointGraph objects.

# If the plot group has child elements like line graphs or point graphs, their properties can be modified by accessing the childs attribute of the PlotGroup1D object.

# After any change, the apply() method must be called to apply the changes to the COMSOL file.

plotgroup = comsol.plot_group_1D(tag='pg7', legendactive=True, legendpos='upperright')
plotgroup.childs[0].expression = 'p'
plotgroup.childs[0].unit = 'MPa'
plotgroup.apply()

# Changes can also be made loading the desired line graph.
line_graph = plotgroup.line_graph(tag='lngr1', expression='p', unit='kPa', legend=True, legendmethod='evaluated', legendpattern='t = eval(t,d) d')
# Which can be later modified.
line_graph.linecolor = 'cyclereset'
line_graph.apply()
# WARNING: The apply() method afects the object and its childs, but not its parents.

# Finally, the export properties can be set. The ones not given will keep their previous value.
# The export() method will save the plot as a PNG file with the given properties. If no path is given, an automatic name will be generated.
comsol.export_properties(width=900, height=600, resolution=96, font_size=22, title=False, legend=True, axes=True, grid=True, logo=False)
plotgroup.export()

# Plot groups can also be duplicated. And then modified independently.
plotgroup2 = plotgroup.duplicate()
plotgroup2.childs[0].expression = 'dl.U'
plotgroup2.ylabel = 'Velocity (m/s)'
plotgroup2.legendlayout = 'outside'
plotgroup2.legendpos = 'right'
plotgroup2.apply()
plotgroup2.export()

# They can also be created from scratch, if 'tag' is not given, as well as their childs.
plotgroup3 = comsol.plot_group_1D(dataset='cln1', label='Mixed Line Graph', legendactive=True, legendpos='upperright', time=[1,3,5], twoyaxes=True)
line1 = plotgroup3.line_graph(expression='p', unit='kPa', xdata='expr', xdataexpr='z', xdataunit='mm')
line2 = plotgroup3.line_graph(expression='dl.U', unit='m/s', xdata='expr', xdataexpr='z', xdataunit='mm', linecolor="cyclereset", linestyle='dashed', plotonsecyaxis=True)
plotgroup3.export()

# The same logic applies to point graphs.
plotgroup4 = comsol.plot_group_1D(tag='pg6', legendactive=True, legendlayout='outside', legendpos='top', legendcolumncount=2)
pointgraph = plotgroup4.point_graph(tag='ptgr1',legend=True, legendmethod='manual', legendmanuallist=['P1', 'P2', 'P3', 'P4', 'P5', 'P6'])
plotgroup4.export()

# Finally, the COMSOL file can be saved with the changes. If no path is given, it will overwrite the original file.
comsol.save("test_plot_group_1D.mph")

# This function apply the changes to all the objects that have been initialized in the ComsolPostprocessor instance.
comsol.apply()
# These functions run and export the plots that have been initialized in the ComsolPostprocessor instance.
comsol.run_all_plots()
comsol.export_all_plots()