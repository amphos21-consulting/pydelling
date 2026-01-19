import unittest
from pydelling.managers.comsol_manager import ComsolManager
from pydelling.utils.configuration_utils import test_data_path
import mph

def skip_comsol_tests():
    try:
        mph.start()
        return False
    except:
        return True


@unittest.skipIf(skip_comsol_tests(), "COMSOL tests are skipped because COMSOL is not installed.")
class ComsolManagerCase(unittest.TestCase):
    def setUp(self):
        # Initialize the ComsolPostprocessor with a test file
        try:
            self.comsol_manager = ComsolManager()

        except:
            self.skipTest("COMSOL model could not be loaded. Ensure the test.mph file is available.")
        

    def test_run(self):
        comsol = self.comsol_manager.comsol_model(file_path=test_data_path() / "test.mph")
        study = comsol.study('std1')
        study.run()


    def test_run_sequence(self):
        comsol = self.comsol_manager.comsol_model(file_path=test_data_path() / "test.mph")
        studies = [comsol.study('std1'), comsol.study('std2')]
        comp = comsol.component('comp1')

        comsol.run_sequence(studies, comp, 'minpt1', 'dl.pA')



    def test_run_parametric_sweep(self):
        comsol = self.comsol_manager.comsol_model(file_path=test_data_path() / "test.mph")
        study = comsol.study('std1')
        values_list = [1e-20, 3e-20, 5e-20, 7e-20] 

        study.run_parametric_sweep("variable",
                           "k",
                           values_list,
                           "var1")        

@unittest.skipIf(skip_comsol_tests(), "COMSOL tests are skipped because COMSOL is not installed.")
class ResultsCase(unittest.TestCase):
    def setUp(self):
        # Initialize the ComsolPostprocessor with a test file
        try:
            self.comsol_manager = ComsolManager()
            self.comsol = self.comsol_manager.comsol_model(file_path=test_data_path() / "test.mph")

        except:
            self.skipTest("COMSOL model could not be loaded. Ensure the test.mph file is available.")
        

    def test_get_variable_evolution_at_point(self):
        t, p = self.comsol.results.get_variable_evolution_at_point('dset1', ['p', 'dl.U'],['pt1', 'pt6'])
        # Assert the results
        self.assertEqual(int(t[34]*10), 34)
        self.assertEqual(int(p[0][0][34]), 7764)
        self.assertEqual(int(p[0][1][34]), 2423)

    def test_point_evaluation_to_excel(self):
        df_test = self.comsol.results.point_evaluation_to_excel(['dset1', 'dset2'], [['p', 'dl.U'], ['p', 'dl.U']], ['pt1', 'pt6'])
        # Check if the DataFrame is not empty
        self.assertFalse(df_test.empty)
        # Check if the DataFrame has the expected columns
        expected_columns = ['t', 'p_pt1', 'dl.U_pt1', 'p_pt6', 'dl.U_pt6']
        self.assertTrue(all(col in df_test.columns for col in expected_columns))
        self.assertEqual(int(df_test['t'][68]*10), 67)
        self.assertEqual(int(df_test['p_pt6'][68]), 46904)

    def test_plot_group_1D(self):
        plotgroup = self.comsol.results.plot_group_1D(tag='pg7', legendactive=True, legendpos='upperright')
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

        plotgroup3 = self.comsol.results.plot_group_1D(dataset='cln1', label='Mixed Line Graph', legendactive=True, legendpos='upperright', time=[1,3,5], twoyaxes=True)
        line1 = plotgroup3.line_graph(expression='p', unit='kPa', xdata='expr', xdataexpr='z', xdataunit='mm')
        line2 = plotgroup3.line_graph(expression='dl.U', unit='m/s', xdata='expr', xdataexpr='z', xdataunit='mm', linecolor="cyclereset", linestyle='dashed', plotonsecyaxis=True)
    
        
        plotgroup4 = self.comsol.results.plot_group_1D(tag='pg6', legendactive=True, legendlayout='outside', legendpos='top', legendcolumncount=2)
        pointgraph = plotgroup4.point_graph(tag='ptgr1',legend=True, legendmethod='manual', legendmanuallist=['P1', 'P2', 'P3', 'P4', 'P5', 'P6'])

    def test_plot_group_2D(self):
        plotgroup = self.comsol.results.plot_group_2D(dataset='dset2', label='New 2D Plot', time=4, selection='all', view='view1', showlegends=True, legendcolor='magenta', legendpos='bottom', showlegendsmaxmin=True, showlegendsunit=True, legendformattingactive=True, legendnotation='engineering', legendprecision=3)
        surface = plotgroup.surface(expression='p', unit='kPa', dataset='dset2', dataset_time='parent', color_table='Dipole', color_table_discrete=7, color_table_reverse=True, color_table_sym=False, rangelist=[0.1,2.8], selection='all')

    def test_export(self):
        plotgroup = self.comsol.results.plot_group_1D(tag='pg7', legendactive=True, legendpos='upperright')
        self.comsol.results.export_properties(width=900, height=600, resolution=96, font_size=22, title=False, legend=True, axes=True, grid=True, logo=False)
        plotgroup.export()
            
    def test_tables(self):
        table = self.comsol.results.table(tag='tbl1', columnheaders=["Temps (d)","P1", "P2", "P3", "P4", "P5", "P6"])
        row = [1]*len(table.get_columnheaders())
        table.add_rows(row)
        table.remove_row(4)
        df = table.get_table()
        self.assertEqual(df['P3'][34],1.7299169311845762e-11)

    def test_derived_values(self):
        dev = self.comsol.results.derived_value('pev1')
        dev.table.clear()
        df = dev.get_result()
        self.assertTrue(df.empty)
        dev.run()
        dev.table.columnheaders = ["Temps (d)","P1", "P2", "P3", "P4", "P5", "P6"]
        dev.table.apply()
        df = dev.get_result()
        self.assertEqual(df['P3'][35],1.7299169311845762e-11)

if __name__ == '__main__':
    unittest.main()
