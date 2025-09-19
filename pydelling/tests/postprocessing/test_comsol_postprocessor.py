import unittest
from pydelling.postprocessing.comsol_postprocessor import ComsolPostprocessor
from pydelling.utils.configuration_utils import test_data_path

@unittest.skip("ComsolManager and ComsolPostprocessor tests only run locally with a valid COMSOL installation.")
class TestComsolPostprocessor(unittest.TestCase):
    def setUp(self):
        # Initialize the ComsolPostprocessor with a test file
        try:
            self.comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
            self.model = self.comsol.model
            self.comp = self.comsol.comp
            self.geom = self.comsol.geom
        except:
            self.skipTest("COMSOL model could not be loaded. Ensure the test.mph file is available.")
        

    def test_get_variable_evolution_at_point(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        t, p = comsol.get_variable_evolution_at_point('dset1', ['p', 'dl.U'],['pt1', 'pt6'])
        # Assert the results
        self.assertEqual(int(t[34]*10), 34)
        self.assertEqual(int(p[0][0][34]), 294)
        self.assertEqual(int(p[0][1][34]), 91)

    def test_point_evaluation_to_excel(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        df_test = comsol.point_evaluation_to_excel(['dset1', 'dset2'], [['p', 'dl.U'], ['p', 'dl.U']], ['pt1', 'pt6'])
        # Check if the DataFrame is not empty
        self.assertFalse(df_test.empty)
        # Check if the DataFrame has the expected columns
        expected_columns = ['t', 'p_pt1', 'dl.U_pt1', 'p_pt6', 'dl.U_pt6']
        self.assertTrue(all(col in df_test.columns for col in expected_columns))
        self.assertEqual(int(df_test['t'][68]*10), 67)
        self.assertEqual(int(df_test['p_pt6'][68]), 44572)

    def test_duplicate_plot(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        new_plot = comsol.model.result().duplicate("pg99", "pg4")
        # Check if the new plot was created successfully
        self.assertIsNotNone(new_plot)
        # Check if the new plot has the expected name
        self.assertEqual(new_plot.tag(), "pg99")

if __name__ == '__main__':
    unittest.main()
