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

### Editing the deck like a dict

A study behaves like a dict of card paths. A path is `/`-separated selectors, each `KEYWORD`
or `KEYWORD name` (case-insensitive). The first one matches a top-level card (looking
through `SUBSURFACE`), the rest direct children, so a path means exactly one place:
`"OUTPUT/TIMES"` is never `CHEMISTRY/OUTPUT`, and
`"FLOW_CONDITION initial/LIQUID_PRESSURE"` is never `TYPE/LIQUID_PRESSURE`.

```python
study["MATERIAL_PROPERTY soil/POROSITY"]            # ['0.25']
study["MATERIAL_PROPERTY soil/POROSITY"] = 0.3      # keeps indentation and comment
study["TIME/FINAL_TIME"] = [1000, "d"]
study["TIME/MAXIMUM_TIMESTEP_SIZE"] = [1e5, "s"]    # appended to TIME if missing

# A list of rows rewrites a block's content in place...
study["GRID/BOUNDS"] = [[0, 0, 0], [10, 1, 1]]
study["REGION east/COORDINATES"] = [[10, 0, 0], [10, 1, 1]]
# ...or replaces a card and all its repeats with one card per row.
study["OUTPUT/TIMES"] = [["d", 50, 100, 150], ["d", 200, 250]]

del study["OUTPUT/SNAPSHOT_FILE"]                   # or = None (no error if missing)
"GRID/BOUNDS" in study                              # True

study.update({                                      # several edits, e.g. from YAML
    "GRID/NXYZ": [200, 1, 1],
    "OUTPUT/MASS_BALANCE": None,
})
```

Reading returns string tokens: a card's arguments, a block's rows, or one row per repeated
card. A path that matches nothing raises `CardNotFound` (a `KeyError`) naming where the
keyword does exist, e.g. `found at: MATERIAL_PROPERTY soil/PERMEABILITY/PERM_ISO`. A missing
card is only appended when its keyword does not already exist deeper in that block, so
`study["MATERIAL_PROPERTY soil/PERM_ISO"] = 1e-12` raises instead of adding a misplaced card.
A block with several same-keyword entries must be named (`REGION west`, not `REGION`).

`study.deck` is the parsed card/block tree (`PflotranDeck`) of the current text. The
selector-tuple API is still available (`get_card`, `get_card_values`, `set_card_values`,
`add_card`, `remove_card`); there each selector matches at any depth below the previous one
unless `direct=True`. Blocks end at their matching `END` or `/`, including nested
sub-blocks, `SKIP`/`NOSKIP` sections and `SUBSURFACE`/`END_SUBSURFACE`. Which cards open
blocks is inferred from known PFLOTRAN keywords and indentation; when the parser has to
guess (e.g. fully unindented decks), it lists the guess in `study.deck.warnings`.

### Samplings and sensitivity cases

The flow is: parameters → samplings → template → studies.

```python
import scipy.stats
from pydelling.managers import (
    LHS, Grid, ParameterSpace, PflotranManager, PflotranStudy, Sampler, Table,
)

# 1. Parameters, in physical units. Every sample is checked against these ranges.
space = ParameterSpace({
    "K": {"bounds": [1e-6, 1e-3], "scale": "log", "units": "m/s"},
    "phi": {"bounds": [0.1, 0.5]},
})

# 2. From one sample to the template placeholders (<<PERM>>, <<PHI>>).
def to_pflotran(sample):
    return {"PERM": sample["K"] * 1.02e-7, "PHI": sample["phi"]}


# 3. Templates: shared card edits once; a variant of the template is a sensitivity case.
base = PflotranStudy("template.in", variable_delimiters=("<<", ">>"))
base["GRID/NXYZ"] = [200, 1, 1]
long_run = base.copy()
long_run["TIME/FINAL_TIME"] = [10, "y"]


# 4. Samplers: built-in ones, or your own (n unit-cube points, one column per parameter).
class Halton(Sampler):
    def points(self, dimension):
        return scipy.stats.qmc.Halton(dimension, seed=self.seed).random(self.n)


# 5. Studies: one line per set, sampler + parameters + template; one study per sample.
manager = PflotranManager()
manager.add_studies(LHS(n=16, seed=42), space, base, variables=to_pflotran)
manager.add_studies(Grid(levels={"K": [1e-5, 1e-4], "phi": [0.2, 0.4]}), space, base, to_pflotran)
manager.add_studies(Halton(n=16, seed=1), space, base, variables=to_pflotran)
manager.add_studies(LHS(n=16, seed=42), space, long_run, variables=to_pflotran,
                    name="lhs-long", metadata={"case": "long"})   # same samples, other case
manager.add_studies(Table("runs/example/samples-lhs.csv", name="replay"), space, base,
                    variables=to_pflotran)                        # samples you already have

manager.select(case="long")                      # manager with those studies only
manager.records()                                # rows: study_id, metadata, sample, simulation_id
manager.requirements(["Total_Tracer [M]"])       # expected outputs, read from each deck
manager.designs["lhs"].to_csv("samples-lhs.csv")  # the samples drawn, per name
```

Studies are named `<name>-000000`, `<name>-000001`… and the template is never modified.
`n=0` adds nothing. `sampler.sample(space)` alone returns the samples (a `Design`)
without building studies. Without `variables`, each sample is passed to the template as is. Every study gets
`study.metadata = {**metadata, "design", "method", "seed", **sample, **variables}`;
`records()` adds a `simulation_id` (hash of the rendered input), so identical inputs share
it whatever design produced them. `study.set_output_times(times, unit="s")` writes
`OUTPUT/TIMES` (10 values per card) and `study.output_times()` reads them back in seconds,
which is what `requirements()` uses.

### Post-processing where the study runs

Callbacks turn a finished run into a small table, **where it ran** (for SSH campaigns, on
the remote host), so only that table has to be downloaded. They are copied with the
template, validated before anything runs, and executed by `LocalExecutor` right after the
solver's outputs pass `check_outputs`.

```python
from pydelling.managers import (Cell, Cells, Domain, ExtractHDF5, FunctionCallback,
                                ObservationPoints, Region)

template.add_postprocess(
    # HDF5 snapshots -> time series: time_s, selection, variable, unit, cell, value,
    # aggregate, n_cells, volume
    ExtractHDF5(
        "Total_*",                                        # dataset names or globs
        {
            "outlet": Cell(x=10.0),                       # nearest cell (None axes ignored)
            "cell_42": Cell(id=42),                       # 1-based natural id, any grid
            "probes": Cells(points=[[2.5, .5, .5], [5.0, .5, .5]]),  # one row per cell
            "inlet": Region("west", aggregate="volume_mean"),  # deck REGION
            "box": Region(box=[[0, 0, 0], [5, 1, 1]], aggregate="max"),
            "mass": Domain("integral"),                   # sum(value * volume)
        },
        times=None,                                       # or seconds to keep
    ),
    # *-obs-*.pft files -> time_s, point, cell, x, y, z, variable, unit, value
    ObservationPoints(variables="Total_*", points=None),
    # anything else: f(workdir, study) -> DataFrame, defined in a module
    FunctionCallback(my_module.final_mass, name="mass_balance"),
)
```

- **Geometry** (`CellGeometry`) is read from the HDF5 `Coordinates` (structured), the
  deck's `.uge` `CELLS` table (explicit unstructured) or HDF5 `Domain/Cells` +
  `Vertices` (implicit unstructured). Before running it comes from the deck's `GRID`
  when possible; otherwise the checks that need it wait for the run.
- **Regions**: `COORDINATES` boxes or points, `COORDINATE`, `BLOCK` and `FILE` (cell ids,
  text or HDF5). On structured grids a box selects the cells it overlaps; a zero-width box
  (a face such as `REGION west`) selects the cells touching it. On unstructured grids, the
  cells whose center is inside.
- **Aggregates**: `mean`, `volume_mean`, `sum`, `integral`, `min`, `max`, or any
  module-level `f(values, volumes) -> float`. `Region`/`Domain` require one.
- **Custom**: subclass `PostprocessCallback` (`process`, `options`, optional `validate`) or
  `Selection` (`cells(geometry, study, workdir)` -> 1-based ids).
- **State**: `status.json` records `postprocess: {name: {state, file, rows, sha256}}` and
  `solver_completed`. A failed callback fails the study; a resume re-runs only the
  callbacks when the solver outputs are unchanged. Each callback's `spec()` is part of the
  batch identity and lets `batch_worker` rebuild it on any host.

## Coming Soon

Detailed documentation for simulation managers is being updated. Please check back soon or refer to the API documentation for specific class details.

For examples, see the `code_snippets/managers/` directory in the repository.
## Reproducible parameter batches

The opt-in batch API preserves legacy `run()` callers:

```python
from pydelling.managers import LHS, LocalExecutor, PflotranManager, PflotranStudy

space = {"permeability": {"bounds": [1e-15, 1e-12], "scale": "log"}}
manager = PflotranManager()
manager.add_studies(LHS(n=4, seed=42), space, PflotranStudy("template.in"))
requirements = manager.requirements(["Total_Tracer [M]"])  # output times read from each deck
result = manager.run_batch(
    LocalExecutor(executable="/path/to/pflotran", workers=4),
    "runs/example", requirements, resume=True,
)
assert result.successful
```

`ParameterSpace` supports fixed values, discrete values, continuous bounds,
weighted disjoint intervals, and generated linear/log partitions. Samplers: `Random`,
`LHS` and `Sobol` (`n` a power of two; both take scipy options such as `scramble=False`),
`Grid(levels={...})` with physical levels, `Table(csv | DataFrame | records)` to replay
samples, or a `Sampler` subclass implementing `points(dimension)`.

`SSHExecutor(host, root, uv, ...)` provides source deployment, detached workers,
status and allowlisted artifact retrieval through OpenSSH. `deploy(workspace,
relative_files)` returns a remote uv runtime. Set `runtime` to that directory and
`local_options` to the remote `LocalExecutor` settings to pass an `SSHExecutor`
directly to `manager.run_batch`. This invokes the generic pydelling batch worker;
no application-specific module is needed. The supplied runtime must contain the
locked pydelling workspace. For complete application pipelines, `start` accepts a
config and a configurable `entrypoint` (default `run_models.py`).

A batch writes each study's files in its own folder (`<campaign>/<study>/`; with
`LocalExecutor(attempts=True)`, one `attempts/0001`, `attempts/0002`… sub-folder per
run so earlier runs are kept), validates HDF5 variables and times, records return
codes and output hashes, rejects changed provenance, and skips intact successful
studies on resume. `LocalExecutor.pipeline(folder)` holds the same campaign lock
across multiple named batches and postprocessing, allowing applications to gate a
training batch on verification. No shell interpolation or global cwd/env mutation
is used for local solver launches.

`PflotranReader` is a context manager. `times_seconds` normalizes supported HDF5
units without changing legacy native-time access, and `cell_centers` computes
structured-grid centroids from face coordinates.
