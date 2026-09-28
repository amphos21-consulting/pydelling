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
## Reproducible parameter batches

The new opt-in API preserves legacy `run()` callers:

```python
from pydelling.managers import (
    ParameterSpace, SamplingConfig, PflotranStudy, PflotranManager, LocalExecutor,
)
space = ParameterSpace({"permeability": {"bounds": [1e-15, 1e-12], "scale": "log"}})
samples = space.sample(SamplingConfig(method="lhs", n=4, seed=42))
base = PflotranStudy("template.in")
manager = PflotranManager()
requirements = {}
for i, values in enumerate(samples.to_dict("records")):
    study = base.copy(study_name=f"case-{i:04d}")
    study.set_variables(**values)
    manager.add_study(study)
    requirements[study.name] = {
        "expected_times": [20000.],  # seconds, regardless of native HDF5 units
        "required_variables": ["Total_Tracer [M]"],
    }
result = manager.run_batch(
    LocalExecutor(executable="/path/to/pflotran", workers=4),
    "runs/example", requirements, resume=True,
)
assert result.successful
```

`ParameterSpace` supports fixed values, discrete values, continuous bounds,
weighted disjoint intervals, and generated linear/log partitions. `SamplingConfig`
supports random/LHS/Sobol/grid designs. Grid levels are physical values supplied
through `options={"levels": {...}}`; Sobol requires a power-of-two size. Additional
unit-cube samplers can be installed through `register_sampler`.

`SSHExecutor(host, root, uv, ...)` provides source deployment, detached workers,
status and allowlisted artifact retrieval through OpenSSH. `deploy(workspace,
relative_files)` returns a remote uv runtime. Set `runtime` to that directory and
`local_options` to the remote `LocalExecutor` settings to pass an `SSHExecutor`
directly to `manager.run_batch`. This invokes the generic pydelling batch worker;
no application-specific module is needed. The supplied runtime must contain the
locked pydelling workspace. For complete application pipelines, `start` accepts a
config and a configurable `entrypoint` (default `run_models.py`).

A batch preserves each attempt, validates HDF5 variables and times, records return
codes and output hashes, rejects changed provenance, and skips intact successful
studies on resume. `LocalExecutor.pipeline(folder)` holds the same campaign lock
across multiple named batches and postprocessing, allowing applications to gate a
training batch on verification. No shell interpolation or global cwd/env mutation
is used for local solver launches.

Use `PflotranStudy.get_card`, `set_card_values`, `add_card`, or `remove_card` with
`direct=True` when subsequent selectors must be direct children (e.g. a flow
condition's pressure value rather than the pressure keyword inside its TYPE card).
The default descendant lookup remains backward-compatible.

`PflotranReader` is a context manager. `times_seconds` normalizes supported HDF5
units without changing legacy native-time access, and `cell_centers` computes
structured-grid centroids from face coordinates.
