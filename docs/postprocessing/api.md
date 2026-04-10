# Postprocessing

The `pydelling.postprocessing` package contains tools for analysing and
summarizing simulation outputs after a model run.

At the moment, this package includes utilities for checking PFLOTRAN mass
balance results, computing residuals, generating summary tables, and producing
error heatmaps.

## Package contents

- `__init__.py`: initializes the `postprocessing` package.
- `mass_balance_check_pflotran.py`: provides tools to evaluate PFLOTRAN mass
  balance files and summarize balance errors across species and simulation runs.

## Main class

### `MassBalanceCheckPflotran`

`MassBalanceCheckPflotran` is used to process one or more PFLOTRAN mass-balance
files. It can:

- read balance files
- identify species-specific global and flux columns
- compute mass-balance residuals
- summarize residuals across species
- combine results from multiple files
- generate heatmaps of percent errors

This makes it useful for checking mass conservation and comparing simulation
results across runs.

## Typical workflow

A typical workflow is:

1. define one or more input patterns pointing to PFLOTRAN mass-balance files
2. create a `MassBalanceCheckPflotran` instance
3. process a single file or summarize all matching files
4. inspect the output tables and generated figures

## Example

```python
from pydelling.postprocessing.mass_balance_check_pflotran import MassBalanceCheckPflotran

checker = MassBalanceCheckPflotran(
    input_patterns="results/**/*.mass_balance",
    outdir="out"
)

checker.summarize_all_files()