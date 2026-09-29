# Tutorials

Comprehensive tutorials for learning pydelling workflows and best practices.

## PFLOTRAN manager

Runnable scripts in `code_snippets/managers/pflotran_manager/`, using a small 1D column
template (`column_template.in`). Run them from any folder; they write to `./studies/`.

1. **`tutorial_01_edit_cards.py` — edit a deck like a dict.** Read and change cards by path
   (`study["GRID/NXYZ"] = [200, 1, 1]`), rewrite coordinate blocks, replace repeated
   `OUTPUT/TIMES` cards, add/remove cards, and see the error a wrong path gives.
2. **`tutorial_02_samplers_and_sensitivity.py` — samplings and sensitivity cases.** Define
   a `ParameterSpace`, generate LHS and grid `Design`s, add them to a `PflotranManager` on
   a base template and on a variant (a sensitivity case), then `select`, `records`, write
   the inputs and sample tables, and replay a design from CSV.

See [Simulation management](../managers/overview.md) for the full API.

## Coming Soon

Interactive tutorials are being developed to help you learn pydelling effectively. These will include:

- **Getting Started Tutorial**: Step-by-step introduction to pydelling
- **Mesh Processing Workshop**: Hands-on mesh preprocessing workflows  
- **Simulation Setup Guide**: Complete simulation preparation tutorial
- **Data Analysis Tutorial**: Post-processing and visualization techniques
- **Advanced Workflows**: Complex multi-physics and uncertainty quantification examples

## Current Resources

While we develop the tutorials, please refer to:

- [Code Snippets](code-snippets.md) for practical examples
- [Usage Guide](../docs-usage.md) for comprehensive documentation
- The `code_snippets/` directory in the repository for working examples

Stay tuned for interactive, step-by-step tutorials!