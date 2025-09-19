from pydelling.managers.comsol_manager import ComsolManager

# First, initialize the ComsolManager with the desired COMSOL version
manager = ComsolManager(version='6.2')

# ComsolManager.ComsolModel is a class that holds the information of each model to run
# In order to run model, we need to define all the needed information

model = manager.ComsolModel(f"test.mph", study='std1')
# Since no save_name is provided, the original file will be overwritten

# Run
manager.run(model)
