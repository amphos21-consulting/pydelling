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

    def test_plot_group_1D(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        plotgroup = comsol.plot_group_1D(tag='pg7', legendactive=True, legendpos='upperright')
        plotgroup.childs[0].expression = 'p'
        plotgroup.childs[0].unit = 'MPa'
        plotgroup.apply()

        line_graph = plotgroup.line_graph(tag='lngr1', expression='p', unit='kPa', legend=True, legendmethod='evaluated', legendpattern='t = eval(t,d) d')
        line_graph.linecolor = 'cyclereset'
        line_graph.apply()

        plotgroup2 = plotgroup.duplicate()
        plotgroup2.childs[0].expression = 'dl.U'
        plotgroup2.ylabel = 'Velocity (m/s)'
        plotgroup2.legendlayout = 'outside'
        plotgroup2.legendpos = 'right'
        plotgroup2.apply()

        plotgroup3 = comsol.plot_group_1D(dataset='cln1', label='Mixed Line Graph', legendactive=True, legendpos='upperright', time=[1,3,5], twoyaxes=True)
        line1 = plotgroup3.line_graph(expression='p', unit='kPa', xdata='expr', xdataexpr='z', xdataunit='mm')
        line2 = plotgroup3.line_graph(expression='dl.U', unit='m/s', xdata='expr', xdataexpr='z', xdataunit='mm', linecolor="cyclereset", linestyle='dashed', plotonsecyaxis=True)
    
        
        plotgroup4 = comsol.plot_group_1D(tag='pg6', legendactive=True, legendlayout='outside', legendpos='top', legendcolumncount=2)
        pointgraph = plotgroup4.point_graph(tag='ptgr1',legend=True, legendmethod='manual', legendmanuallist=['P1', 'P2', 'P3', 'P4', 'P5', 'P6'])

    def test_plot_group_2D(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        plotgroup = comsol.plot_group_2D(dataset='dset2', label='New 2D Plot', time=4, selection='all', view='view1', showlegends=True, legendcolor='magenta', legendpos='bottom', showlegendsmaxmin=True, showlegendsunit=True, legendformattingactive=True, legendnotation='engineering', legendprecision=3)
        surface = plotgroup.surface(expression='p', unit='kPa', dataset='dset2', dataset_time='parent', color_table='Dipole', color_table_discrete=7, color_table_reverse=True, color_table_sym=False, rangelist=[0.1,2.8], selection='all')

    def test_export(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        plotgroup = comsol.plot_group_1D(tag='pg7', legendactive=True, legendpos='upperright')
        comsol.export_properties(width=900, height=600, resolution=96, font_size=22, title=False, legend=True, axes=True, grid=True, logo=False)
        plotgroup.export()
            
    def test_tables(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        table = comsol.table(tag='tbl1', columnheaders=["Temps (d)","P1", "P2", "P3", "P4", "P5", "P6"])
        row = [1]*len(table.get_columnheaders())
        table.add_rows(row)
        table.remove_row(4)
        df = table.get_table()
        self.assertEqual(df['P3'][34],3.4035563429902708e-12)

    def test_derived_values(self):
        comsol = ComsolPostprocessor(file_path=test_data_path() / "test.mph")
        dev = comsol.derived_value('pev1')
        dev.table.clear()
        df = dev.get_result()
        self.assertTrue(df.empty)
        dev.run()
        dev.table.columnheaders = ["Temps (d)","P1", "P2", "P3", "P4", "P5", "P6"]
        dev.table.apply()
        df = dev.get_result()
        self.assertEqual(df['P3'][35],3.4035563429902708e-12)
if __name__ == '__main__':
    unittest.main()
