import unittest
from pydelling.postprocessing.comsol_postprocessor import ComsolPostprocessor
from pydelling.utils.configuration_utils import test_data_path
import mph

def skip_comsol_tests():
    try:
        mph.start()
        return False
    except:
        return True

@unittest.skipIf(skip_comsol_tests(), "COMSOL tests are skipped because COMSOL is not installed.")
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

    def test_edit_surface_plot(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        surface1 = comsol.ComsolSurface(
            dataset = 'parent',
            expression = 'p',
            unit = 'kPa',
            color_table = 'Rainbow',
            color_table_discrete = 10,
            color_table_reverse = False,
            color_table_sym = False,
            rangelist = None,
            selection = False,
        )

        surface2 = comsol.ComsolSurface(
            dataset = 'parent',
            expression = 'dl.U',
            unit = 'm/s',
            color_table = 'Dipole',
            color_table_discrete = 10,
            color_table_reverse = False,
            color_table_sym = False,
            rangelist = None,
            selection = [2],
        )

        comsol.edit_surface_plot(True,'pg4', [surface1, surface2], label="Mix", dataset='dset1', time=5)

    def test_edit_line_graph(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        line1 = comsol.ComsolLine(
            dataset = 'cln1',
            expression = 'p',
            unit = 'kPa',
            xdata = 'expr',
            xdataexpr = 'z',
            xdataunit = 'mm',
            dataset_param="parent"
        )

        line2 = comsol.ComsolLine(
            dataset = 'cln1',
            expression = 'dl.U',
            unit = 'm/s',
            xdata = 'expr',
            xdataexpr = 'z',
            xdataunit = 'mm',
            dataset_param="parent",
            linecolor="cyclereset"
        )
        comsol.edit_line_graph(True,'pg7', [line1, line2], label="Line_Mix", time=[1,3,5])

    def test_edit_point_graph(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        line1 = comsol.ComsolLine(
            dataset = 'parent',
            expression = 'p',
            unit = 'kPa',
            xdata = 'expr',
            xdataexpr = 't',
            xdataunit = 'd',
            dataset_param="parent",
            marker="cycle",
            selection=[7,4,10],
            linestyle='none',
        )

        comsol.edit_point_graph(True,'pg6', line1, label="Evolution", time="all")

if __name__ == '__main__':
    unittest.main()
