from pydelling.managers.comsol_manager import ComsolManager

# First, initialize the ComsolManager with the desired COMSOL version
manager = ComsolManager(version='6.2')

# ComsolManager.ComsolModel is the object that manage a COMSOL file
comsol = manager.comsol_model(f"test.mph", study='std1')
# The ComsolStudy object is stored in the ComsolModel.studies list

# Run. Since no save_name is provided, the original file will be overwritten
comsol.studies[0].run()

# or the study can be loaded once the file is already loaded
study = comsol.study('std1')
study.run()
