from pydelling.managers.comsol_manager import ComsolManager

# First, initialize the ComsolManager with the desired COMSOL version and open the file
comsol_manager = ComsolManager(version='6.2')
comsol = comsol_manager.comsol_model(file_path=r"../test.mph")

# !NOTE: La idea de este snippet es hacer una función en ComsolPostprocessor que te cree un PlotGroup1D (o use uno ya existente) y te lo devuelva con la evolución de las concentraciones/volumen mineral/fracción masica en un punto/average/integral de todas las fases a partir de un cierto threshold