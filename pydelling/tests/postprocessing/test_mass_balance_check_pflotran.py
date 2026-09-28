import unittest
import os
import tempfile

from pydelling.postprocessing.mass_balance_check_pflotran import MassBalanceCheckPflotran
from pydelling.utils.configuration_utils import test_data_path


class TestMassBalanceCheckPflotran(unittest.TestCase):
    # Test initialization of MassBalanceCheckPflotran Class
    def test_setUp(self):
        with tempfile.TemporaryDirectory() as output_dir:
            MassBalanceCheckPflotran(
                os.path.join(test_data_path(), "**", "*-mas.dat"),
                outdir=output_dir,
            )

    # Test generation of mass balance summary
    def test_summary(self):
        with tempfile.TemporaryDirectory() as output_dir:
            checker = MassBalanceCheckPflotran(
                os.path.join(test_data_path(), "**", "*-mas.dat"),
                outdir=output_dir,
            )
            checker.summarize_all_files()
            self.assertTrue(
                os.path.isfile(
                    os.path.join(output_dir, "mass_balance_percent_error_matrix.png")
                )
            )


if __name__ == "__main__":
    unittest.main()
