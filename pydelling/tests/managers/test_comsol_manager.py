import unittest
from pydelling.managers.comsol_manager import ComsolManager
from pydelling.utils.configuration_utils import test_data_path

@unittest.skip("ComsolManager and ComsolPostprocessor tests only run locally with a valid COMSOL installation.")
class TestComsolManager(unittest.TestCase):
    def setUp(self):
        # Initialize the ComsolPostprocessor with a test file
        try:
            self.comsol_manager = ComsolManager(version='6.2')
        except:
            self.skipTest("COMSOL model could not be loaded. Ensure the test.mph file is available.")
        

    def test_run(self):
        self.model = self.comsol_manager.ComsolModel(file_path=test_data_path() / "test.mph", study='std1')
        self.comsol_manager.run(self.model)


    def test_run_sequence(self):
        self.model = self.comsol_manager.ComsolModel(file_path=test_data_path() / "test.mph", study=['std1','std2'])
        self.comsol_manager.run_sequence_studies(self.model)


    def test_run_parametric_sweep(self):
        modellistssweep = []

        for i in range(5):
            modellistssweep.append(
                self.comsol_manager.ComsolModel(f"{test_data_path()}/test.mph",
                            study='std1',
                            parameter_type='var',
                            variable_tag='var1',
                            parameter='k',
                            parameter_value=f"{(i+1)*1e-20:.2g} [m^2]",
                            )
                )
        self.comsol_manager.run_parametric_sweep(modellistssweep)
    
if __name__ == '__main__':
    unittest.main()
