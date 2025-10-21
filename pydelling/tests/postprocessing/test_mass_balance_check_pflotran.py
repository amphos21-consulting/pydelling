import unittest
from pydelling.utils.configuration_utils import test_data_path
from pydelling.postprocessing.mass_balance_check_pflotran import MassBalanceCheckPflotran
import os

class TestMassBalanceCheckPflotran(unittest.TestCase):

    #Test initialization of MassBalanceCheckPflotran Class
    def test_setUp(self):
        checker = MassBalanceCheckPflotran(os.path.join(test_data_path(), "**", "*-mas.dat"), outdir=test_data_path())
    
    #Test generation of mass balance summary
    def test_summary(self):
        checker = MassBalanceCheckPflotran(os.path.join(test_data_path(), "**", "*-mas.dat"), outdir=test_data_path())
        checker.summarize_all_files()

if __name__ == '__main__':
    unittest.main()