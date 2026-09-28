# Simulation Management Overview

The managers module provides tools for running and coordinating numerical simulations across different software platforms.

## Available Managers

### PFLOTRAN Manager
- Automated PFLOTRAN simulation workflows
- Parameter studies and sensitivity analysis
- Local and HPC execution support

### COMSOL Manager  
- COMSOL batch processing
- Parametric sweeps
- Result extraction and analysis

## PFLOTRAN studies

A `PflotranStudy` wraps one input deck used as a template. Each case of a parameter study is
a copy of it with its own values, and a manager writes and runs them.

### Template placeholders

```python
from pydelling.managers import PflotranManager, PflotranStudy

base = PflotranStudy("rc1_training_template.in", variable_delimiters=("<<", ">>"))
base.placeholders()            # {'PERM', 'PHI', ...}

manager = PflotranManager()
for i, sample in enumerate(samples):
    case = base.copy(study_name=f"case-{i:03d}")   # independent copy
    case.set_variables(**sample)
    manager.add_study(case)                          # assigns case.idx = position
manager.generate_run_files("./studies")
```

Rendering is strict: a placeholder without a value raises `MissingTemplateVariables` listing
all missing names (`missing_variables()` returns them without raising). Pass `strict=False`
for the pre-1.2.1 behaviour of rendering unknown placeholders as empty text. Without
`variable_delimiters` the usual Jinja `{{ name }}` syntax is used.

### Editing the deck by card path

`study.deck` is a parsed card/block tree (`PflotranDeck`) of the current text. Cards are
selected by a path of `KEYWORD` or `KEYWORD name` selectors, each matching at any depth below
the previous one:

```python
study.get_card_values("MATERIAL_PROPERTY soil", "POROSITY")          # ['0.25']
study.set_card_values("MATERIAL_PROPERTY soil", "PERM_ISO", values=1e-12)
study.set_card_values("TIME", "FINAL_TIME", values=[10, "y"])
study.add_card("MATERIAL_PROPERTY soil", line="TORTUOSITY 0.5")
study.remove_card("OUTPUT", "SNAPSHOT_FILE")
study.deck.find_all("REGION", blocks_only=True)                      # REGION blocks, not references
```

Edits keep indentation and inline comments. Blocks end at their matching `END` or `/`,
including nested sub-blocks, `SKIP`/`NOSKIP` sections and `SUBSURFACE`/`END_SUBSURFACE`.
Which cards open blocks is inferred from known PFLOTRAN keywords and indentation. When the
parser has to guess (e.g. fully unindented decks), it lists the guess in `study.deck.warnings`
and logs it.

## Coming Soon

Detailed documentation for simulation managers is being updated. Please check back soon or refer to the API documentation for specific class details.

For examples, see the `code_snippets/managers/` directory in the repository.