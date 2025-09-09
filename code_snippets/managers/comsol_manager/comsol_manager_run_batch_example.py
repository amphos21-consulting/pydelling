from pydelling.managers.comsol_manager import ComsolManager
from shutil import copyfile

# First, initialize the ComsolManager with the desired COMSOL version
manager = ComsolManager(version='6.2')

# ComsolManager.ComsolModel is a class that holds the information of each model to run
# In order to run a batch of models, we create a list of ComsolModel instances
# For this example, we will copy the test model with different names and run them in batch

modellists = []

for i in range(5):
    copyfile("test.mph", f"test{i+1}.mph")

    # In this example the ComsolModel instances are appended inside the loop after copying the files,
    # but they can be appended individually if needed
    modellists.append(
        manager.ComsolModel(f"test{i+1}.mph", study='std1')
        )

# Finally, run the batch of models
manager.run_batch(modellists)
