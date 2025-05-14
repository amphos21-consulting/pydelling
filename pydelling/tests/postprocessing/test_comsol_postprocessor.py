import unittest
from pydelling.postprocessing.comsol_postprocessor import ComsolPostprocessor
from pydelling.utils.configuration_utils import test_data_path

class TestComsolPostprocessor(unittest.TestCase):
    def test_initialization(self):
        # Test if the initialization sets up the client and model correctly
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        model = comsol.model
        comp = comsol.comp
        geom = comsol.geom
        

    def test_get_variable_evolution_at_point(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        t, p = comsol.get_variable_evolution_at_point('dset1', ['p', 'dl.U'],['pt1', 'pt6'])
        # Assert the results
        self.assertEqual(int(t[34]*10), 34)
        self.assertEqual(int(p[0][0][34]), 294)
        self.assertEqual(int(p[0][1][34]), 91)

    def test_point_evaluation_to_excel(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        df_test = comsol.point_evaluation_to_excel(['dset1', 'dset2'], [['p', 'dl.U'], ['p', 'dl.U']], ['pt1', 'pt6'], export=False)
        # Check if the DataFrame is not empty
        self.assertFalse(df_test.empty)
        # Check if the DataFrame has the expected columns
        expected_columns = ['t', 'p_pt1', 'dl.U_pt1', 'p_pt6', 'dl.U_pt6']
        self.assertTrue(all(col in df_test.columns for col in expected_columns))
        self.assertEqual(int(df_test['t'][68]*10), 67)
        self.assertEqual(int(df_test['p_pt6'][68]), 44572)

if __name__ == '__main__':
    unittest.main()