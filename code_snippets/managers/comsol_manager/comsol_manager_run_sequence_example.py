from pydelling.managers.comsol_manager import ComsolManager

# First, initialize the ComsolManager with the desired COMSOL version
manager = ComsolManager(version='6.2')

# ComsolManager.ComsolModel is a class that holds the information of each model to run
# In order to run a batch of studies within the same comsol file, a single ComsolModel instance
# must be provided with a list of studies tags

model_sequence = manager.ComsolModel(f"test.mph",
                                     study=['std1','std2'],
                                     save_name="test_sequence.mph"
                                     )

# Finally, run the sequence
manager.run_sequence_studies(model_sequence)
