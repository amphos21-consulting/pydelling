from pydelling.postprocessing.mass_balance_check_pflotran import MassBalanceCheckPflotran
import os

BASE_FOLDER = "code_snippets\postprocessing\pflotran_mass_balance\cases"
INPUT_PATTERNS = [os.path.join(BASE_FOLDER, "**", "*-mas.dat")]

#Initialize the mass balance checker with the input and output directories.
#The mass balance cheqcker will look for all .mass_balance files in the input directory.
checker = MassBalanceCheckPflotran(INPUT_PATTERNS, outdir="code_snippets/postprocessing/pflotran_mass_balance/results")

# prints & saves combined summary + heatmap
checker.summarize_all_files()    