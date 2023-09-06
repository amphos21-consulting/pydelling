from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pydelling.managers import PflotranManager, PflotranStudy

from pydelling.managers.callbacks.BaseCallback import BaseCallback
from pathlib import Path
from pydelling.managers.ssh.steps import CopyStep


class PflotranRestartCallback(BaseCallback):
    """Callback to restart Pflotran simulations."""
    study: PflotranStudy
    def __init__(self, manager: PflotranManager,
                 study: PflotranStudy,
                 kind: str = 'post',
                 on_remote: bool = False, **kwargs):
        super().__init__(manager, study, 'pre', on_remote=on_remote, **kwargs)

    def run(self):
        """This method should detect the hdf5 file in the previous study and copy it to the current study"""
        on_remote = self.kwargs['on_remote'] if 'on_remote' in self.kwargs else False
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
                self.study.add_restart(f'input_files/{target_file.name}')
        else:
            files = self.manager.ssh.ls
            if self.study.idx > 0:
                prev_study: PflotranStudy = list(self.manager.studies.values())[self.study.idx - 1]
            else:
                return
            output_files = self.manager.ssh.ls_dir(f'../{prev_study.output_folder.name}')
            # Copy the input
            target_file = None
            for file in output_files:
                if 'restart' in file:
                    target_file = f"{self.manager.ssh.pwd}/{file}"
                    final_file = f"{self.manager.ssh.pwd}/../{self.study.output_folder.name}/input_files/{Path(file).name}"
                    copy_step = CopyStep(target_file, final_file, remote=True)
                    self.study.add_ssh_step(copy_step)
                    self.study.add_restart(f'input_files/{Path(file).name}')
            if target_file is None:
                raise FileNotFoundError('Restart file not found')

    def run_dummy(self):
        """This method is called when the callback is run in dummy mode"""
        pass


