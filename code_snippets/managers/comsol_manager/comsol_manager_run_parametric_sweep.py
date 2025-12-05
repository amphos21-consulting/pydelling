from pydelling.managers.comsol_manager import ComsolManager


# First, initialize the ComsolManager with the desired COMSOL version
manager = ComsolManager(version='6.2')

# ComsolManager.ComsolModel is the object that manage a COMSOL file
comsol = manager.comsol_model(f"test.mph")
# And the study
study = comsol.study('std1')

# Then we create the list of the values we want to change
values_list = ["1e-20 [m^2]", "3e-20 [m^2]", "5e-20 [m^2]", "7e-20 [m^2]"]
# values_list = [1e-20, 3e-20, 5e-20, 7e-20] also works

# And we run the parametric sweep
study.run_parametric_sweep("variable",
                           "k",
                           values_list,
                           "var1")
# The results will be stored in a different file for each parameter value
