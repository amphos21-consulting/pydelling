from pydelling.postprocessing.comsol_postprocessor import ComsolPostprocessor

# First, initialize the ComsolPostprocessor with the desired COMSOL version and open the file
comsol = ComsolPostprocessor(file_path=r"test.mph", version='6.2')

# This function edits an existing or creates a new 1D plot group in the COMSOL file.

# The plot group properites can be modified with the parameters of the function. See pydelling documentation to find all possible parameters. For direct acces to API, use ._api attribute of the PlotGroup2D or Surface objects.

# If the plot group has child elements like surfaces, their properties can be modified by accessing the childs attribute of the PlotGroup2D object.

# After any change, the apply() method must be called to apply the changes to the COMSOL file.

plotgroup = comsol.plot_group_2D(tag='pg1', label="Pressure 2D", legendpos='bottom')
plotgroup.childs[0].expression = 'p'
plotgroup.childs[0].unit = 'MPa'
plotgroup.apply()

# Changes can also be made loading the desired surface.
surface = plotgroup.surface(tag='surf1', expression='p', unit='kPa', dataset='dset2', dataset_time='parent', color_table='Dipole', color_table_discrete=7)
# Which can be later modified.
surface.color_table_reverse = True
surface.rangelist = [0.1,2.8]
surface.apply()
# WARNING: The apply() method afects the object and its childs, but not its parents.

# Finally, the export properties can be set. The ones not given will keep their previous value.
# The export() method will save the plot as a PNG file with the given properties. If no path is given, an automatic name will be generated.
comsol.export_properties(width=900, height=600, resolution=96, font_size=22, title=False, legend=True, axes=True, grid=True, logo=False)
plotgroup.export()

# Plot groups can also be duplicated. And then modified independently.
plotgroup2 = plotgroup.duplicate()
plotgroup2.childs[0].expression = 'dl.U'
plotgroup2.childs[0].color_table = 'HeatCamera'
plotgroup2.childs[0].rangelist = False
plotgroup2.apply()
plotgroup2.export()

# They can also be created from scratch, if 'tag' is not given, as well as their childs.
plotgroup3 = comsol.plot_group_2D(dataset='dset2', label='New 2D Plot', time=2, selection='all', view='view1', showlegends=True, legendcolor='magenta', legendpos='left', showlegendsmaxmin=True, showlegendsunit=True, legendformattingactive=True, legendnotation='engineering', legendprecision=3)
surface3 = plotgroup3.surface(expression='p', unit='kPa', dataset='dset2', dataset_time='parent', color_table='Dipole', color_table_discrete=7, color_table_reverse=True, color_table_sym=False, rangelist=[0.1,2.8], selection='all')
plotgroup3.export()

# Finally, the COMSOL file can be saved with the changes. If no path is given, it will overwrite the original file.
comsol.save("test_plot_group_2D.mph")

# This functions apply the changes, run and export the plots that have been initialized in the ComsolPostprocessor instance.
comsol.apply()
comsol.run_all_plots()
comsol.export_all_plots()