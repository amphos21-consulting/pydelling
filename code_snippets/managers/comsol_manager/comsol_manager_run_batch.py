from pydelling.managers.comsol_manager import ComsolManager
from shutil import copyfile

# First, initialize the ComsolManager with the desired COMSOL version
manager = ComsolManager(version='6.2')

# ComsolManager.ComsolModel is the object that manage a COMSOL file
# A ComsolModel has a subclass ComsolStudy
# In order to run a batch of models, we create a list of ComsolStudy instances
# For this example, we will copy the test model with different names and run them in batch

study_lists = []

for i in range(5):
    copyfile("test.mph", f"test{i+1}.mph")

# Here we open each file and study
for i in range(5):
    comsol = manager.comsol_model(f"test{i+1}.mph")
    study_lists.append(comsol.study('std1'))

# Finally, run the batch of models
manager.run_batch(study_lists)
