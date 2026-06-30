"""
Callback to restart Pflotran simulations.


"""

from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pydelling.managers import PflotranManager, PflotranStudy

from pydelling.managers.callbacks.base_callback import BaseCallback
from pathlib import Path
from pydelling.managers.ssh.steps import CopyStep


class PflotranRestartCallback(BaseCallback):
    """Callback that wires a previous PFLOTRAN restart file into the next study.

    Category: PFLOTRAN callback.
    Tags: pflotran, restart, callback, local, remote.
    Use when: an MCP agent needs to understand how sequential PFLOTRAN studies
        reuse restart HDF5 files.
    """

    study: PflotranStudy
    def __init__(self, manager: PflotranManager,
                 study: PflotranStudy,
                 kind: str = 'post',
                 on_remote: bool = False, **kwargs):
        """Create a restart callback for a PFLOTRAN study.

        Category: PFLOTRAN callback.
        Tags: pflotran, restart, callback, initialization.
        Use when: adding restart-file propagation to a study sequence.
        Args:
            manager: Manager containing the ordered study collection.
            study: Current study that should receive the previous restart file.
            kind: Callback kind retained for API compatibility.
            on_remote: Whether restart handling should use remote SSH steps.
            **kwargs: Extra callback parameters forwarded to ``BaseCallback``.
        Side effects:
            Initializes the callback as a pre-run callback.
        """
        super().__init__(manager, study, 'pre', on_remote=on_remote, **kwargs)

    def run(self, on_remote):
        """Attach the previous study's restart file to the current study.

        Category: PFLOTRAN callback.
        Tags: pflotran, restart, callback, ssh, hdf5.
        Use when: running a sequence where each study should start from the
            prior study's restart output.
        Args:
            on_remote: If ``True``, add a remote copy step through the manager's
                SSH connection; otherwise copy/register a local file.
        Raises:
            FileNotFoundError: If no restart HDF5 file is found in the previous
                study outputs.
        Side effects:
            Adds input/restart references to the study and may add a remote
            ``CopyStep``.
        """
        if not on_remote:
            if self.study.idx > 0:
                prev_study: PflotranStudy = list(self.manager.studies.values())[self.study.idx - 1]
            else:
                return
            output_files = list(prev_study.output_folder.glob('*.h5'))
            target_file = None
            for file in output_files:
                if 'restart' in file.name:
                    target_file = file
            if target_file is None:
                raise FileNotFoundError('Restart file not found')
            else:
                self.study.add_input_file(target_file)
                self.study.add_restart(f'./input_files/{target_file.name}')
        else:
            if self.study.idx > 0:
                prev_study: PflotranStudy = list(self.manager.studies.values())[self.study.idx - 1]
            else:
                return
            self.manager.ssh.cd_studies_folder(self.manager.studies_folder_name)
            output_files = self.manager.ssh.ls_dir(f'./{prev_study.output_folder.name}')
            # Copy the input
            target_file = None
            for file in output_files:
                if 'restart' in file:
                    target_file = f"{self.manager.ssh.pwd}/{prev_study.output_folder.name}/{file}"
                    final_file = f"{self.manager.ssh.pwd}/{self.study.output_folder.name}/input_files/{Path(file).name}"
                    copy_step = CopyStep(target_file, final_file, remote=True)
                    self.study.add_ssh_step(copy_step)
                    self.study.add_restart(f'./input_files/{Path(file).name}')
            if target_file is None:
                raise FileNotFoundError('Restart file not found')

    def run_dummy(self):
        """Handle dummy callback execution.

        Category: PFLOTRAN callback.
        Tags: pflotran, restart, dummy-run.
        Use when: the manager is writing files without executing simulations.
        Notes:
            This callback intentionally performs no work in dummy mode.
        """
        pass
