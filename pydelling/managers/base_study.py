"""
This class contains the core methods for all the other child Manager classes.
A manager is supposed to control the simulations run on a given software automatically.

The manager should be able to:
- Create the input files for the software
- Modify the input files for the software
- Run the software
- Read the output status of the simnulation

The idea to process the input files is the following:
- Read the raw input file
- The user can add variables to change, or can specify directly on the input file using {{var}} notation (jinja2)
- The input file is rendered using jinja2 for each specific case


"""

from __future__ import annotations
import copy as _copy
from pathlib import Path
from jinja2 import Environment, StrictUndefined, Undefined, meta
import shutil
from pydelling.utils import UnitConverter
from typing import Callable

from typing import TYPE_CHECKING, List, Union
if TYPE_CHECKING:
    from pydelling.managers import BaseCallback, BaseManager
    from pydelling.managers.postprocess import PostprocessCallback
    from pydelling.managers.ssh.steps import BaseStep

import logging

logger = logging.getLogger(__name__)

DEFAULT_VARIABLE_DELIMITERS = ('{{', '}}')


class MissingTemplateVariables(KeyError):
    """Raised when a strict study is rendered without values for all its placeholders."""

    def __init__(self, missing, input_file_name=None):
        self.missing = sorted(missing)
        self.input_file_name = input_file_name
        super().__init__(f"Template '{input_file_name}' has no value for: {', '.join(self.missing)}")

    def __str__(self):
        return self.args[0]


class BaseStudy(UnitConverter):
    """Base class for templated simulation studies and input-file generation.

    Category: manager
    Tags: study, simulation, jinja, input-files, callbacks
    Usage: implementing software-specific study managers that render templates, copy inputs, and run hooks.
    """
    count = 0  # Only used to build default study names; the manager assigns ``idx``.
    shared_folder_default_name = 'shared_folder'
    results_folder_name = None

    def __init__(self,
                 input_file: str,
                 study_name: str = None,
                 is_independent: bool = False,
                 input_file_name: str = None,
                 variable_delimiters: tuple = DEFAULT_VARIABLE_DELIMITERS,
                 strict: bool = True,
                 ):
        """Initialize a study from a template input file.

        Category: manager
        Tags: study, template, input-file, initialization
        Usage: subclasses need common state for rendering input files and managing auxiliary files.

        Args:
            variable_delimiters: start/end strings of template placeholders, e.g. ``('<<', '>>')``
                for ``<<PERM>>``. With non-default delimiters, Jinja block and comment syntax is
                moved to ``<%``/``%>`` and ``<#``/``#>`` so ``{% %}``/``{# #}`` in the deck are
                left untouched.
            strict: if True, rendering raises :class:`MissingTemplateVariables` when any
                placeholder has no value (instead of silently rendering it empty).

        Returns:
            None: stores template text, settings, callbacks, and file registries.
        """
        if not is_independent:
            self.idx = self.__class__.count
            self.__class__.count += 1
            self.is_independent = False
        else:
            self.idx = None
            self.is_independent = True
        self.name = study_name if study_name is not None else f"{self.__class__.__name__}-{self.idx + 1}"
        self.input_file_name = input_file_name if input_file_name is not None else Path(input_file).name
        logger.info(f"Initializing {self.__class__.__name__} study (input template: {input_file})")
        self.input_file = Path(input_file)
        self.settings = {}
        self.jinja_settings = {}
        # Step 1: read and set the input file
        self.raw_text = self.input_file.read_text()
        self.aux_files = {}
        # Free-form description of the study (design, sample, case…), see BaseManager.records
        self.metadata = {}
        self.output_folder = None
        self.variable_delimiters = tuple(variable_delimiters)
        self.strict = strict
        # (callback class, kwargs) pairs, bound to the study in initialize_callbacks
        self._callbacks: List[tuple] = []
        self.callbacks: List[BaseCallback] = []
        # Post-processing callbacks run where the study ran, see add_postprocess
        self.postprocess: List[PostprocessCallback] = []
        self.steps: List[BaseStep] = []
        self._shared_files = []


    def pre_run(self):
        """Hook executed before a study run.

        Category: manager
        Tags: study, hook, pre-run, lifecycle
        Usage: subclasses need to prepare files or state before execution.

        Returns:
            None: base implementation does nothing.
        """
        pass

    def post_run(self):
        """Hook executed after a study run.

        Category: manager
        Tags: study, hook, post-run, lifecycle
        Usage: subclasses need to collect outputs or cleanup after execution.

        Returns:
            None: base implementation does nothing.
        """
        pass

    def _replace_with_jinja_variable(self, var, var_name=None, value=None):
        """Replace text in the template and register a Jinja variable value.

        Category: manager
        Tags: study, jinja, template, replace
        Usage: scripts need a raw input token converted into a render-time variable.

        Returns:
            None: updates raw_text and jinja_settings.
        """
        logger.debug(f"Replacing {var} with jinja variable")
        if var_name is None:
            var_name = var
        self.raw_text = self.raw_text.replace(var, f"{var_name}")
        self.jinja_settings[var_name] = value


    def replace_variable(self, var, value=None):
        """Register a template variable replacement.

        Category: manager
        Tags: study, jinja, variable, replace
        Usage: scripts need to set a value that will be injected during render.

        Returns:
            None: updates the Jinja settings for the variable.
        """
        logger.info(f"Replacing {var} with value {value}")
        self._replace_with_jinja_variable(var, value=value)


    def _find_tags(self, tag: str, ignore_case: bool = True, equal: bool = True):
        """Find non-comment lines containing a tag.

        Category: util
        Tags: study, text, tags, line-index
        Usage: subclass managers need to locate editable sections in an input template.

        Returns:
            list: line indexes containing the tag.
        """
        logger.debug(f"Finding tag '{tag}'")
        lines = self.raw_text.splitlines()
        if ignore_case:
            lines = [line.lower() for line in lines]
            tag = tag.lower()
        # Delete lines starting with #
        # lines = [line for line in lines if not line.startswith('#')]
        line_idx = [i for i, line in enumerate(lines) if tag in line]
        # if equal:
        #     lines_strip = [line.strip().split()[0] for line in lines]
        #     print(lines_strip)
        #     line_idx = [i for i in line_idx if lines[i].strip().strip()[0] == tag]
        #     print(line_idx)
        # Clean for comments
        line_idx = [i for i in line_idx if not lines[i].startswith('#')]
        return line_idx

    def _find_tags_in_subset(self, tags: list, subset: list, ignore_case: bool = True):
        """Find lines in a subset that contain any requested tag.

        Category: util
        Tags: study, text, tags, subset
        Usage: parsers need tag matching inside a previously extracted block.

        Returns:
            list: subset-relative line indexes containing any tag.
        """
        logger.debug(f"Finding tags '{tags}' in subset")
        if ignore_case:
            subset = [line.lower() for line in subset]
            tags = [tag.lower() for tag in tags]
        return [i for i, line in enumerate(subset) if any(tag in line for tag in tags)]

    def _get_line(self, line_index: int):
        """Return one line from the raw input text.

        Category: util
        Tags: study, text, line, lookup
        Usage: subclass managers need direct access to a template line by index.

        Returns:
            str: requested raw text line.
        """
        return self.raw_text.splitlines()[line_index]

    def _add_line(self, line_index: int, new_line: list, sep: str = ' '):
        """Insert one line into the raw input text.

        Category: util
        Tags: study, text, insert, line-edit
        Usage: subclass managers need to add a generated input-deck line.

        Returns:
            None: mutates raw_text.
        """
        logger.debug(f"Adding line {line_index} with {new_line}")
        lines = self.raw_text.splitlines()
        if isinstance(new_line, str):
            new_line = [new_line]
        lines.insert(line_index, sep.join(new_line))
        self.raw_text = '\n'.join(lines)

    def _delete_line(self, line_index: int):
        """Delete one line from the raw input text.

        Category: util
        Tags: study, text, delete, line-edit
        Usage: subclass managers need to remove an input-deck line.

        Returns:
            None: mutates raw_text.
        """
        logger.debug(f"Deleting line {line_index}")
        lines = self.raw_text.splitlines()
        del lines[line_index]
        self.raw_text = '\n'.join(lines)

    def _delete_lines(self, line_indexes: list):
        """Delete multiple lines from the raw input text.

        Category: util
        Tags: study, text, delete, line-edit
        Usage: subclass managers need to remove several input-deck lines safely.

        Returns:
            None: mutates raw_text.
        """
        logger.debug(f"Deleting lines {line_indexes}")
        lines = self.raw_text.splitlines()
        for line_index in sorted(line_indexes, reverse=True):
            del lines[line_index]
        self.raw_text = '\n'.join(lines)

    def _add_lines(self, line_index: int, new_lines: list, sep: str = ' '):
        """Insert multiple lines into the raw input text.

        Category: util
        Tags: study, text, insert, line-edit
        Usage: subclass managers need to add a generated input-deck block.

        Returns:
            None: mutates raw_text.
        """
        logger.debug(f"Adding lines {line_index} with {new_lines}")
        lines = self.raw_text.splitlines()
        for i, new_line in enumerate(new_lines):
            if isinstance(new_line, str):
                new_line = [new_line]
            lines.insert(line_index + i, sep.join(new_line))
        self.raw_text = '\n'.join(lines)

    def _get_nth_previous_line(self, line_index: int, n: int = 1):
        """Return a line before a given index.

        Category: util
        Tags: study, text, previous-line, lookup
        Usage: parsers need context before a matched line.

        Returns:
            str: line at line_index - n.
        """
        return self.raw_text.splitlines()[line_index - n]

    def _get_nth_next_line(self, line_index: int, n: int = 1):
        """Return a line after a given index.

        Category: util
        Tags: study, text, next-line, lookup
        Usage: parsers need context after a matched line.

        Returns:
            str: line at line_index + n.
        """
        return self.raw_text.splitlines()[line_index + n]

    def _replace_line(self, line_index: int, new_line: list, sep: str = ' '):
        """Replace one line in the raw input text.

        Category: util
        Tags: study, text, replace, line-edit
        Usage: subclass managers need to update an input-deck line by index.

        Returns:
            None: mutates raw_text.
        """
        logger.debug(f"Replacing line {line_index} with {new_line}")
        lines = self.raw_text.splitlines()
        lines[line_index] = sep.join(new_line)
        self.raw_text = '\n'.join(lines)

    def render(self, **kwargs):
        """Render the input template with Jinja settings.

        Category: manager
        Tags: study, jinja, render, input-file
        Usage: scripts need the final input text for a study case.

        Returns:
            str: rendered input text.
        """
        logger.info(f"Rendering input file {self.input_file_name}")
        if self.strict:
            missing = self.missing_variables(**kwargs)
            if missing:
                raise MissingTemplateVariables(missing, self.input_file_name)
        template = self._jinja_environment().from_string(self.raw_text)
        return template.render({**self.jinja_settings, **kwargs})

    def _jinja_environment(self) -> Environment:
        """Build the Jinja environment for this study's delimiters and strictness."""
        start, end = self.variable_delimiters
        options = dict(
            variable_start_string=start,
            variable_end_string=end,
            keep_trailing_newline=True,
            undefined=StrictUndefined if self.strict else Undefined,
        )
        if self.variable_delimiters != DEFAULT_VARIABLE_DELIMITERS:
            options.update(block_start_string=f'{start[0]}%', block_end_string=f'%{end[-1]}',
                           comment_start_string=f'{start[0]}#', comment_end_string=f'#{end[-1]}')
        return Environment(**options)

    def placeholders(self) -> set:
        """Return the names of all variables referenced by the template.

        Category: manager
        Tags: study, jinja, template, placeholders
        Usage: validating that a parameter set covers every placeholder before rendering.

        Returns:
            set: undeclared template variable names.
        """
        environment = self._jinja_environment()
        return set(meta.find_undeclared_variables(environment.parse(self.raw_text)))

    def missing_variables(self, **kwargs) -> list:
        """Return the sorted placeholders that have no value yet.

        Category: manager
        Tags: study, jinja, template, validation
        Usage: checking a study before writing it to disk.

        Returns:
            list: placeholder names absent from the Jinja settings and ``kwargs``.
        """
        return sorted(self.placeholders() - set(self.jinja_settings) - set(kwargs))

    def set_variables(self, **values):
        """Set values for several template placeholders at once.

        Category: manager
        Tags: study, jinja, variable, parameters
        Usage: applying one sampled parameter set to a study.

        Returns:
            None: updates the Jinja settings.
        """
        logger.debug(f"Setting template variables {values}")
        self.jinja_settings.update(values)


    def add_auxiliary_file(self, file_path: str):
        """Register an auxiliary input file for this study.

        Category: manager
        Tags: study, auxiliary-file, input-file, copy
        Usage: generated case folders need extra files copied alongside the rendered input.

        Returns:
            None: stores the file path by basename.
        """
        logger.info(f"Adding auxiliary file {file_path}")
        file_path = Path(file_path)
        self.aux_files[file_path.name] = file_path

    def add_input_file(self, file_path: Union[Path, str], shared_file=False):
        """Register an input file for the generated study case.

        Category: manager
        Tags: study, input-file, shared-file, copy
        Usage: a rendered case needs supporting files copied into its input folder.

        Returns:
            None: stores the file and optionally marks it as shared.
        """
        logger.info(f"Adding input file {file_path}" + ("(Shared file)" if shared_file else ""))
        # Check if the file exists
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File {file_path} not found")
        file_path = Path(file_path)
        self.aux_files[file_path.name] = file_path
        if shared_file:
            self._shared_files.append(file_path.name)

    def add_input_folder(self, folder_path: str, shared_file=False):
        """Register every file in an input folder.

        Category: manager
        Tags: study, input-folder, shared-file, copy
        Usage: a case needs a group of support files copied into generated folders.

        Returns:
            None: registers each direct child file.
        """
        folder_path = Path(folder_path)
        for file in folder_path.glob('*'):
            self.add_input_file(file, shared_file=shared_file)
        logger.info(f"Adding input folder {folder_path} with {len(self.aux_files)} files" + ("(Shared files)" if shared_file else ""))

    def add_callback(self, callback: Callable, kind: str = 'pre', **kwargs):
        """Register a manager callback for this study.

        Category: manager
        Tags: study, callback, lifecycle, manager
        Usage: scripts need custom pre-run or post-run behavior attached to a study.

        Returns:
            None: stores a callback factory for later initialization.
        """
        kwargs['kind'] = kind
        self._callbacks.append((callback, kwargs))

    def add_postprocess(self, *callbacks: PostprocessCallback) -> None:
        """Post-process this study's outputs where it runs, right after the solver.

        Each callback returns a table saved as ``processed/<name>.parquet`` next to the
        outputs (for remote runs, on the remote host), so only that table needs to be
        downloaded. Callbacks are copied with :meth:`copy`, so adding them to a template adds
        them to every study made from it.

        Args:
            *callbacks: e.g. ``ExtractHDF5(...)``, ``ObservationPoints()`` or any
                :class:`~pydelling.managers.postprocess.PostprocessCallback`.

        Raises:
            ValueError: If a name is unsafe or already used by a callback of this study.

        Example:
            ```python
            template.add_postprocess(
                ExtractHDF5("Total_*", {"outlet": Cell(x=10.0)}),
                ObservationPoints(),
            )
            ```
        """
        from pydelling.managers.postprocess.base import check_name

        for callback in callbacks:
            check_name(callback.name)
            if any(existing.name == callback.name for existing in self.postprocess):
                raise ValueError(f"{self.name} already has a postprocess callback named "
                                 f"'{callback.name}'")
            self.postprocess.append(callback)

    def add_ssh_step(self, step: BaseStep):
        """Register an SSH execution step for this study.

        Category: manager
        Tags: study, ssh, step, execution
        Usage: remote execution workflows need ordered setup or run steps.

        Returns:
            None: appends the validated step to steps.
        """
        from pydelling.managers.ssh.steps import BaseStep
        assert isinstance(step, BaseStep), 'Step must be a subclass of BaseStep'
        self.steps.append(step)
        logger.debug(f"Adding ssh step {step.__class__.__name__}")

    def remove_ssh_steps(self):
        """Remove all registered SSH steps.

        Category: manager
        Tags: study, ssh, steps, reset
        Usage: scripts need to clear remote execution steps before rebuilding them.

        Returns:
            None: clears the steps list.
        """
        self.steps = []

    def initialize_callbacks(self, manager: BaseManager):
        """Instantiate callback objects for a manager.

        Category: manager
        Tags: study, callbacks, manager, lifecycle
        Usage: a manager is preparing runnable callback instances for a study.

        Returns:
            None: populates callbacks from registered callback factories.
        """
        self.callbacks = [callback(manager, self, **kwargs) for callback, kwargs in self._callbacks]

    def to_shared_folder(self,
                         shared_folder_name='./shared_folder',
                         results_folder_name=None,
                         ):
        """Copy shared input files into the shared folder.

        Category: writer
        Tags: study, shared-files, copy, input-files
        Usage: multiple generated studies should reference common auxiliary files.

        Returns:
            None: creates the shared folder and copies missing shared files.
        """
        BaseStudy.shared_folder_default_name = shared_folder_name
        logger.debug(f"Copying input files to shared folder ({shared_folder_name})")
        shared_folder = Path() / results_folder_name if results_folder_name is not None else Path()
        shared_folder = shared_folder / shared_folder_name
        shared_folder.mkdir(exist_ok=True)
        for file in self.aux_files:
            if file in self._shared_files:
                # Check if it is already in the shared folder
                if not (shared_folder / file).exists():
                    shutil.copy(self.aux_files[file], shared_folder / file)

    def to_file(self,
                output_folder: str=None,
                output_file: str=None,
                auxiliary_folder: str=None,
                **kwargs):
        """Render the study input and write the generated case folder.

        Category: writer
        Tags: study, render, input-file, auxiliary-files
        Usage: scripts need a complete runnable study folder from a template.

        Returns:
            None: writes the rendered input file and copies auxiliary files.
        """

        self.output_folder = output_folder if output_folder is not None else self.name
        # Get the results folder name (previously set by the manager)
        self.results_folder_name = Path(self.output_folder).parent.name

        logger.info(f"Saving input files to {self.output_folder}")
        output_folder = Path(self.output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        output_file = output_folder / (output_file if output_file is not None else Path(self.input_file_name))
        output_file.write_text(self.render(**kwargs))

        # Copy the auxiliary files
        if len(self._shared_files) > 0:
            self.to_shared_folder(results_folder_name=self.results_folder_name)
        if len(self.aux_files) > 0:
            auxiliary_folder = auxiliary_folder if auxiliary_folder is not None else 'input_files'
            auxiliary_folder = output_folder / auxiliary_folder
            auxiliary_folder.mkdir(parents=True, exist_ok=True)
            for aux_file in self.aux_files:
                # Only copy if it is not in the shared folder
                if aux_file not in self._shared_files:
                    shutil.copy(self.aux_files[aux_file], auxiliary_folder / aux_file)
                # Otherwise, copy it from the shared folder
                else:
                    shutil.copy(self.shared_path_default / aux_file, auxiliary_folder / aux_file)

    @property
    def shared_path_default(self):
        """Return the default shared-file folder path.

        Category: manager
        Tags: study, shared-files, path
        Usage: case generation needs to locate previously copied shared inputs.

        Returns:
            pathlib.Path: path to the shared folder.
        """
        project_name = 'studies'
        if self.results_folder_name is not None:
            project_name = self.results_folder_name
        else:
            self.results_folder_name = project_name

        return Path() / project_name / self.shared_folder_default_name

    def to_tar(self):
        """Create a gzip tarball containing generated input files.

        Category: writer
        Tags: study, tar, archive, input-files
        Usage: scripts need a portable archive of a rendered study case.

        Returns:
            None: writes a .tar file for the study output folder.
        """
        import tarfile
        import os
        logger.info(f"Creating tar file {self.output_folder}.tar")
        self.to_file(output_folder='temp')
        # Create tar file using gzip compression
        with tarfile.open(f"{self.output_folder}.tar", "w:gz") as tar:
            tar.add('temp', arcname=os.path.basename('temp'))
        shutil.rmtree('temp')

    def __repr__(self):
        return f"{self.__class__.__name__} (input template: {self.input_file.name})"

    # Properties
    # Attributes a copy must not inherit: identity is new, run state is reset.
    _copy_skip_attrs = ('idx', 'name', 'callbacks', 'output_folder')
    # Attributes copied as new containers holding the same elements (e.g. SSH steps).
    _copy_shallow_attrs = ('steps',)

    def copy(self, study_name: str = None):
        """Return an independent copy of the study.

        Category: manager
        Tags: study, copy, clone
        Usage: scripts need a duplicate study object before changing parameters.

        Template text, variables, files and callback registrations are deep-copied, so
        changing the copy never affects the original. The copy gets a new name (``study_name``
        or the next default name) and no ``idx`` until it is added to a manager.

        Returns:
            BaseStudy: copied study instance.
        """
        new_obj = self.__class__(self.input_file, study_name=study_name)
        for attr, value in self.__dict__.items():
            if attr in self._copy_skip_attrs:
                continue
            if attr in self._copy_shallow_attrs:
                value = _copy.copy(value)
            else:
                value = _copy.deepcopy(value)
            setattr(new_obj, attr, value)
        return new_obj



    def __str__(self):
        return self.__repr__()
