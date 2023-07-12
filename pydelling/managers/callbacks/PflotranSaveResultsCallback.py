from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pydelling.managers import PflotranManager, PflotranStudy

from pydelling.managers.callbacks.BaseCallback import BaseCallback
from pydelling.managers import PflotranPostprocessing
from pathlib import Path
import shutil
import logging
import h5py

logger = logging.getLogger(__name__)


class PflotranSaveResultsCallback(BaseCallback):
    """Callback to save the results of a Pflotran simulation.

    Arguments:
        move: bool = False -> If True, the results are moved instead of copied
        postprocess: bool = False -> If True, the results are postprocessed
        postprocess_regular: bool = False -> If True, the results are postprocessed assuming they are part of a regular grid
    """
    move: bool = False
    postprocess: bool = False
    def __init__(self, manager: PflotranManager,
                 study: PflotranStudy,
                 kind: str = 'post',
                 **kwargs):
        super().__init__(manager, study, 'post', **kwargs)

    def run(self):
        """This callback runs after the simulation is run, it creates a folder and copies (or moves) the results to it"""
        move = self.kwargs['move'] if 'move' in self.kwargs else False
        postprocess = self.kwargs['postprocess'] if 'postprocess' in self.kwargs else False
        postprocess_regular = self.kwargs['postprocess_regular'] if 'postprocess_regular' in self.kwargs else False

        output_files = list(self.study.output_folder.glob('*h5'))
        target_folder = Path(self.manager.results_folder / 'merged_results')
        target_folder.mkdir(exist_ok=True, parents=True)
        for file in output_files:
            if 'restart' in file.name:
                continue
            if file.stem[-1] == 'y':
                continue
            if move:
                # Check if the file already exists
                if (target_folder / file.name).exists():
                    target_file = target_folder / file.name
                    target_file.unlink()
                shutil.move(str(file), str(target_folder.absolute()))
            else:
                shutil.copy(str(file), str(target_folder.absolute()))

        if postprocess:
            import os
            domain_folder = list(self.manager.studies.values())[0].output_folder / 'input_files'
            domain_file = list(domain_folder.glob('*-domain.h5'))[0]
            shutil.copy(domain_file, self.manager.results_folder / 'merged_results')
            old_cwd = os.getcwd()
            logger.info('Postprocessing results')
            pflotran_postprocesser = PflotranPostprocessing()
            # Change the working directory to the results folder
            os.chdir(self.manager.results_folder / 'merged_results')
            pflotran_postprocesser.run()
            os.chdir(old_cwd)
        elif postprocess_regular:
            merged_folder = self.manager.results_folder / 'merged_results'
            h5_files = list(Path(merged_folder).glob('*.h5'))
            merged_filename = f'{merged_folder}/{h5_files[0].stem.split("-")[0]}-merged.h5'
            if Path(merged_filename).exists():
                Path(merged_filename).unlink()
            h5_files = list(Path(merged_folder).glob('*.h5'))

            # Order the files by the number in the file name
            h5_files.sort(key=lambda x: int(x.name.split('-')[-1].split('.')[0]))
            # Delete if exists

            h5_merged = h5py.File(f'{merged_folder}/{h5_files[0].stem.split("-")[0]}-merged.h5', 'w')
            # Add the 'Coordinates' and the 'Provenance' datasets from the first file
            first_file = h5py.File(h5_files[0], 'r')
            h5_merged.create_group('Coordinates')
            h5_merged.create_dataset('Coordinates/X [m]', data=first_file['Coordinates']['X [m]'])
            # Add attributes
            h5_merged.create_dataset('Coordinates/Y [m]', data=first_file['Coordinates']['Y [m]'])
            h5_merged.create_dataset('Coordinates/Z [m]', data=first_file['Coordinates']['Z [m]'])
            h5_merged.create_group('Provenance')
            provenance_keys = first_file['Provenance'].keys()
            map(lambda x: h5_merged['Provenance'].create_dataset(x, data=first_file['Provenance'][x]), provenance_keys)
            first_file.close()
            for file in h5_files:
                with h5py.File(file, 'r') as h5:
                    col = [col_name for col_name in h5.keys() if 'Time' in col_name][0]
                    group = h5_merged.create_group(col)
                    group_keys = h5[col].keys()
                    group_attrs = list(h5[col].attrs.items())
                    group.attrs.create(group_attrs[0][0], group_attrs[0][1])
                    for key in group_keys:
                        h5_merged[col].create_dataset(key, data=h5[col][key])

            # Delete the original files
            # for file in h5_files:
            #     file.unlink()






