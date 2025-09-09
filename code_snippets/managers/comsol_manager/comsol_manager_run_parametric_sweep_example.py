from pydelling.managers.comsol_manager import ComsolManager


# First, initialize the ComsolManager with the desired COMSOL version
manager = ComsolManager(version='6.2')

# ComsolManager.ComsolModel is a class that holds the information of each model to run
# In order to run the parametric sweep, we create a list of ComsolModel instances
# where each instance has a different parameter value

modellistssweep = []

for i in range(5):
    # In this example test.mph is the base model in which the parameter will be changed
    # Since the parameter to change is a variable, the tag of the variable library where is stored
    # must be provided (variable_tag), if its defined as a global parameter variable_tag is not needed
    # In this example the parameter that will change is permeability and its value
    # will change from 1e-20 to 5e-20 m^2

    # Since no save_name is provided, an automatic name will be given to each model:
    # [orignal_name]_[parameter_name]_[parameter_value].mph

    # If you have a different files for each parameter value, its better to use run_batch instead of
    # run_parametric_sweep

    modellistssweep.append(
        manager.ComsolModel(f"test.mph",
                      study='std1',
                      parameter_type='var',
                      variable_tag='var1',
                      parameter='k',
                      parameter_value=f"{(i+1)*1e-20:.2g} [m^2]",
                      )
        )
# Finally, run the parametric sweep
manager.run_parametric_sweep(modellistssweep)
