"""
Module documentation.


"""

from __future__ import annotations

from .base_manager import BaseManager
from . import PflotranStudy
import subprocess
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from pydelling.utils import create_results_folder
from pydelling.managers.pflotran_postprocessing import PflotranPostprocessing
import logging
import os
import getpass

if TYPE_CHECKING:
    from pydelling.managers.ssh import BaseSsh

logger = logging.getLogger(__name__)

class PflotranManager(BaseManager):
    """Manager for writing, running, and collecting PFLOTRAN studies.

    Category: PFLOTRAN management.
    Tags: pflotran, studies, execution, docker, hpc, jureca, lumi, results.
    Usage: to understand how pydelling launches
        ``PflotranStudy`` objects locally, in Docker, or on remote HPC systems
        and how it gathers results afterward.
    """

    def run_batch(self, executor, folder, requirements, *, resume=True, provenance=None, batch_name='batch'):
        """Execute registered studies with durable status, validation and resume.

        Unlike legacy ``run``, this opt-in API returns a BatchResult and never
        assumes PETSc contains the system MPI launcher.
        """
        return executor.run_batch(self.studies.values(), folder, requirements,
                                  resume=resume, provenance=provenance, batch_name=batch_name)

    def _get_study_status(self, study_id: int):
        """Return status information for a PFLOTRAN study.

        Category: PFLOTRAN management.
        Tags: pflotran, status, study.
        Usage: extending the manager with study status queries.
        Args:
            study_id: Integer identifier of the study to inspect.
        Notes:
            This base implementation is a placeholder.
        """
        pass

    def _run_study(self,
                   study: PflotranStudy,
                   n_cores: int = 1,
                   petsc_dir: str = '/opt/pflotran-dev/petsc',
                   petsc_arch: str = 'arch-linux-c-opt',
                   pflotran_dir: str = 'pflotran',
                   **kwargs,
                   ):
        """Run one PFLOTRAN study on the local machine.

        Category: PFLOTRAN management.
        Tags: pflotran, local-execution, petsc, mpi.
        Usage: a study should be executed by a local PFLOTRAN binary rather
            than Docker or a remote HPC backend.
        Args:
            study: ``PflotranStudy`` whose input file has been written to its
                output folder.
            n_cores: Number of MPI ranks. ``1`` uses serial execution.
            petsc_dir: PETSc installation path used for parallel runs.
            petsc_arch: PETSc architecture name used for parallel runs.
            pflotran_dir: PFLOTRAN executable or command path.
            **kwargs: Accepted for compatibility with ``BaseManager`` dispatch.
        Side effects:
            Runs a subprocess in ``study.output_folder`` and sets PETSc
            environment variables for parallel execution.
        """
        if n_cores == 1:
            # Run the study in serial
            subprocess.run([pflotran_dir, '-pflotranin', study.input_file_name], cwd=study.output_folder.absolute())
        else:
            # Run the study in parallel
            os.environ['PETSC_DIR'] = petsc_dir
            os.environ['PETSC_ARCH'] = petsc_arch
            subprocess.call([f'$PETSC_DIR/$PETSC_ARCH/bin/mpirun -np {n_cores} {pflotran_dir} -pflotranin {study.input_file_name}'],
                           cwd=study.output_folder.absolute(),
                           shell=True
                           )

    def _run_study_docker(self,
                          study: PflotranStudy,
                          docker_image: str,
                          n_cores: int = 1,
                          **kwargs,
                          ):
        """Run one PFLOTRAN study inside a Docker container.

        Category: PFLOTRAN management.
        Tags: pflotran, docker, container, execution.
        Usage: PFLOTRAN should run from a Docker image instead of the host
            environment.
        Args:
            study: ``PflotranStudy`` whose run folder is copied into the
                container.
            docker_image: Image used to create the PFLOTRAN container when it is
                not already running.
            n_cores: Number of MPI ranks. ``1`` uses serial execution.
            **kwargs: Accepted for compatibility with ``BaseManager`` dispatch.
        Side effects:
            Creates or starts a container, archives the study folder into it,
            runs PFLOTRAN, then stops and removes the container.
        """
        try:
            import docker
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Docker execution requires the 'pydelling[hpc]' extra."
            ) from exc
        docker_client = docker.from_env()
            # Run the study in serial

        try:
            docker_client.api.start(self.manager_name)
            container = docker_client.containers.get(self.manager_name)
        except Exception:
            docker_client.api.create_container(
                name=self.manager_name,
                image=docker_image,
                command='/bin/sh',
                detach=True,
                tty=True,
                volumes=['/home/pflotran/'],
                host_config=docker_client.api.create_host_config(
                    binds={
                        Path().cwd() / f'studies/{study.name}': {
                            'bind': f'/home/pflotran/{study.name}',
                            'mode': 'rw',
                        }
                    })
            )
            docker_client.api.start(container=self.manager_name)
            container = docker_client.containers.get(self.manager_name)

        # Compress study folder to a tar file
        bytes_io = BytesIO()
        import tarfile
        pw_tar = tarfile.TarFile(fileobj=bytes_io, mode='w')
        pw_tar.add(study.output_folder, arcname=study.output_folder.name)
        pw_tar.close()
        bytes_io.seek(0)
        # volume = docker_client.volumes.create(name=study.output_folder.name, driver='local', driver_opts={'type': 'none', 'device': study.output_folder, 'o': 'bind'})
        # Copy the tar file to the container
        container.exec_run(cmd="bash -c 'cd /home/pflotran'")
        container.put_archive('/home/pflotran', bytes_io)
        container.exec_run(cmd="bash -c 'ls'")
        if n_cores == 1:
            container.exec_run(cmd=f"sudo bash -c 'export PATH=$PATH:/home/pflotran/pflotran/src/pflotran &&"
                                   f" cd /home/pflotran/{study.output_folder.name} && "
                                   f"pflotran -pflotranin {study.input_file_name}'")
        else:
            container.exec_run(cmd=f"sudo bash -c 'export PATH=$PATH:/home/pflotran/pflotran/src/pflotran && "
                                   f"export PETSC_DIR=/home/pflotran/petsc && "
                                   f"export PETSC_ARCH=docker-petsc && "
                                   f"cd /home/pflotran/{study.output_folder.name} && "
                                   f"$PETSC_DIR/$PETSC_ARCH/bin/mpiexec -np {n_cores} pflotran -pflotranin {study.input_file_name}'")
        container.stop()
        container.remove()

    def _run_study_jureca(self,
                            study: PflotranStudy,
                            user,
                            project_name,
                            pkey_path,
                            n_cores: int = 1,
                            wallclock_limit: str = None,
                            shell_script_path: str = None,
                            download_file_extensions: list = None,
                            download_results: bool = True,
                            **kwargs,
                            ):
        """Run one PFLOTRAN study on JURECA through SSH.

        Category: PFLOTRAN management.
        Tags: pflotran, jureca, ssh, hpc, job-submission.
        Usage: dispatching a PFLOTRAN study to the JURECA HPC environment
            with a provided submission script.
        Args:
            study: ``PflotranStudy`` to upload and run.
            user: Remote username.
            project_name: JURECA project or allocation name.
            pkey_path: SSH private key path.
            n_cores: Number of requested cores, retained for dispatch
                compatibility.
            wallclock_limit: Optional wallclock limit retained for compatibility
                with run configuration.
            shell_script_path: Local submission script template. ``{input_name}``
                is replaced with the study input filename before upload.
            download_file_extensions: File suffixes to download after job
                completion.
            download_results: Whether to download result files after the job.
            **kwargs: Extra backend options accepted for compatibility.
        Raises:
            ValueError: If no submission script is provided.
        Side effects:
            Prompts for a password if needed, creates remote folders, uploads
            files, submits a job, waits for completion, and may download results.
        """
        from pydelling.managers.ssh import JurecaSsh

        if self.password is None:
            self.password = getpass.getpass(prompt='Password: ', stream=None)

        self.ssh = JurecaSsh(user=user,
                             project_name=project_name,
                             pkey_path=pkey_path,
                             password=self.password,
                             )
        # Create a folder for the set of studies
        self.ssh.cd_project()
        self.ssh.mkdir(self.studies_folder_name)
        # Create a folder for the study, delete it if it already exists
        self.ssh.cd(self.studies_folder_name)
        if study.name in self.ssh.ls:
            self.ssh.rmdir(study.name)
        self.ssh.mkdir(study.name)
        # Copy the study folder to the server
        self.copy_study_to_remote(self.ssh, study=study)
        for step in study.steps:
            if step.kind == 'pre':
                step.run(manager=self)

        # Copy the shell_script to the server
        if shell_script_path is not None:
            # Read the shell script and replace the study name where {input_name} is found\
            with open(shell_script_path, 'r') as f:
                shell_script = f.read()
            shell_script = shell_script.replace('{input_name}', study.input_file_name)
            # Write to temporary file
            with open('temp.sh', 'w') as f:
                f.write(shell_script)
            # Delete the temporary file
            self.ssh.cp('temp.sh', f"{study.name}/{Path(shell_script_path).name}")
            os.remove('temp.sh')
            # Run the shell script
            self.ssh.send_job(f"{study.name}/{Path(shell_script_path).name}")
            # Get the highest job id
            job_id = max(self.ssh.user_queue['JOBID'])
            # pflotran_status = PflotranStatus()
            self.ssh.wait_for_job(job_id)
            # Copy the results back to the local machine
            # Detect files ending with .h5
            if download_results:
                self._ssh_download(
                    study=study,
                    file_ext=download_file_extensions,
                    job_id=job_id,
                )

        else:
            raise ValueError('shell_script should be provided with the details of the job submission.')


    def _run_study_lumi(self,
                            study: PflotranStudy,
                            user,
                            project_name,
                            pkey_path,
                            n_cores: int = 1,
                            wallclock_limit: str = None,
                            shell_script_path: str = None,
                            download_file_extensions = None,
                            download_results: bool = True,
                            **kwargs,
                            ):
        """Run one PFLOTRAN study on LUMI through SSH.

        Category: PFLOTRAN management.
        Tags: pflotran, lumi, ssh, hpc, job-submission.
        Usage: dispatching a PFLOTRAN study to the LUMI HPC environment with
            a provided submission script.
        Args:
            study: ``PflotranStudy`` to upload and run.
            user: Remote username.
            project_name: LUMI project or allocation name.
            pkey_path: SSH private key path.
            n_cores: Number of requested cores, retained for dispatch
                compatibility.
            wallclock_limit: Optional wallclock limit retained for compatibility
                with run configuration.
            shell_script_path: Local submission script template. ``{input_name}``
                is replaced with the study input filename before upload.
            download_file_extensions: File suffixes to download after job
                completion.
            download_results: Whether to download result files after the job.
            **kwargs: Extra backend options accepted for compatibility.
        Raises:
            ValueError: If no submission script is provided.
        Side effects:
            Prompts for a password if needed, creates remote folders, uploads
            files, submits a job, waits for completion, and may download results.
        """
        from pydelling.managers.ssh import LumiSsh

        if self.password is None:
            self.password = getpass.getpass(prompt='Password: ', stream=None)

        self.ssh = LumiSsh(user=user,
                             project_name=project_name,
                             pkey_path=pkey_path,
                             password=self.password,
                             )
        # Create a folder for the set of studies
        self.ssh.cd_scratch()
        self.ssh.mkdir(self.studies_folder_name)
        # Create a folder for the study, delete it if it already exists
        self.ssh.cd(self.studies_folder_name)
        if study.name in self.ssh.ls:
            self.ssh.rmdir(study.name)
        self.ssh.mkdir(study.name)
        # Copy the study folder to the server
        # self.ssh.cpdir(study.output_folder, study.name)
        self.copy_study_to_remote(self.ssh, study=study)
        for step in study.steps:
            if step.kind == 'pre':
                step.run(manager=self)
        # Copy the shell_script to the server
        if shell_script_path is not None:
            # Read the shell script and replace the study name where {input_name} is found\
            with open(shell_script_path, 'r') as f:
                shell_script = f.read()
            shell_script = shell_script.replace('{input_name}', study.input_file_name)
            # Write to temporary file
            with open('temp.sh', 'w') as f:
                f.write(shell_script)
            # Delete the temporary file
            self.ssh.cp('temp.sh', f"{study.name}/{Path(shell_script_path).name}")
            os.remove('temp.sh')
            # Run the shell script
            self.ssh.send_job(f"{study.name}/{Path(shell_script_path).name}")
            # Get the highest job id
            job_id = None
            while job_id is None:
                import time
                try:
                    job_id = max(self.ssh.user_queue['JOBID'])
                except ValueError:
                    logger.warning('No jobs found in the queue. Waiting for 5 seconds.')
                    time.sleep(5)
            # pflotran_status = PflotranStatus()
            self.ssh.wait_for_job(job_id, check_interval=6)
            # Copy the results back to the local machine
            if download_results:
                self._ssh_download(
                    study=study,
                    file_ext=download_file_extensions,
                    job_id=job_id,
                )

        else:
            raise ValueError('shell_script should be provided with the details of the job submission.')


    def copy_study_to_remote(self,
                            ssh_manager: BaseSsh,
                            study: PflotranStudy,
                            ):
        """Upload a study folder and its auxiliary files to a remote backend.

        Category: PFLOTRAN management.
        Tags: pflotran, ssh, upload, shared-files, input-files.
        Usage: preparing a remote HPC study directory while avoiding repeated
            uploads of shared auxiliary input files.
        Args:
            ssh_manager: Connected SSH/SFTP helper for the target platform.
            study: Study whose output folder and auxiliary files should be
                uploaded.
        Side effects:
            Creates remote shared/input folders, uploads files through SFTP, and
            copies shared files remotely when possible.
        """
        # Check if the shared files are already in the remote server
        if self.has_shared_files:
            if PflotranStudy.shared_folder_default_name not in ssh_manager.ls:
                ssh_manager.mkdir(PflotranStudy.shared_folder_default_name)
            shared_folder_ls = ssh_manager.ls_dir(PflotranStudy.shared_folder_default_name)
            for file in study._shared_files:
                # Get ls of the shared folder
                if file not in shared_folder_ls:
                    ssh_manager.cp(study.aux_files[file], f"{PflotranStudy.shared_folder_default_name}/{file}")

        # Copy the study folder to the server excepting the 'input_files' folder
            # Create the input_files folder
            for file in study.output_folder.glob('*'):
                if file.name != 'input_files':
                    ssh_manager.cp(file.absolute(), str(Path(study.name) / file.name))
            # Copy the aux files to the server, excepting the shared files
            ssh_manager.mkdir(f"{study.name}/input_files")
            for file in study.aux_files:
                if file not in study._shared_files:
                    ssh_manager.cp(study.aux_files[file], f"{study.name}/input_files/{file}")
                else:
                    # Copy the shared files from the shared folder to the input_files folder
                    initial_file = f"{self.ssh.pwd}/{PflotranStudy.shared_folder_default_name}/{file}"
                    final_file = f"{self.ssh.pwd}/{study.name}/input_files/{file}"
                    ssh_manager.cp_remote(f"{initial_file}", f"{final_file}")
        else:
            ssh_manager.cpdir(study.output_folder, study.name)


    @property
    def has_shared_files(self):
        """Return whether any registered study declares shared auxiliary files.

        Category: PFLOTRAN management.
        Tags: pflotran, shared-files, studies.
        Usage: deciding whether remote uploads should use the shared-file
            optimization path.
        Returns:
            bool: ``True`` when at least one study has entries in
            ``_shared_files``.
        """
        return any([len(study._shared_files) > 0 for study in self.studies.values()])

    def _ssh_download(self,
                      study: PflotranStudy,
                      file_ext=None,
                      job_id=None,
                      ):
        """Download selected remote result files into a study output folder.

        Category: PFLOTRAN management.
        Tags: pflotran, ssh, download, results, hdf5.
        Usage: collecting files produced by a remote PFLOTRAN job after the
            queue reports completion.
        Args:
            study: Study whose local output folder receives downloaded files.
            file_ext: Optional list of suffixes to match. Defaults to ``[".h5"]``.
            job_id: Optional job id used to also match scheduler output files.
        Side effects:
            Attempts to download matching remote files through ``self.ssh`` and
            logs warnings for files that cannot be retrieved.
        """
        print(file_ext)
        if file_ext is None:
            file_ext = ['.h5']
        dir_list = self.ssh.ls
        for ext in file_ext:
            ext_files = [file for file in dir_list if Path(file).suffix == ext]
            dir_list += ext_files
        if job_id is not None:
            ext_files = [file for file in dir_list if str(job_id) in file]
            dir_list += ext_files
        for file in dir_list:
            try:
                self.ssh.get(f"{file}", study.output_folder / file)
            except Exception:
                logger.warning(f"Could not download {file}.")



    def merge_results(self, move=False, postprocess=True):
        """Merge HDF5 results from all studies into one results folder.

        Category: PFLOTRAN management.
        Tags: pflotran, results, merge, hdf5, postprocessing.
        Usage: a batch of PFLOTRAN studies should be consolidated for
            combined post-processing.
        Args:
            move: If ``True``, move result files instead of copying them.
            postprocess: If ``True``, copy the domain file and run
                ``PflotranPostprocessing`` in the merged folder.
        Side effects:
            Creates a merged results folder, copies or moves HDF5 files, may
            copy the domain HDF5 file, changes the current working directory, and
            may run PFLOTRAN post-processing.
        """
        self.run(dummy=True)
        import shutil
        # results_folder = create_results_folder(list(self.studies.values())[0].output_folder)
        self.merged_folder = create_results_folder(self.results_folder / 'merged_results')
        for study in self.studies.values():
            hdf5_files = list(study.output_folder.glob('*.h5'))
            for file in hdf5_files:
                if 'restart' not in file.name:
                    if not move:
                        shutil.copy(file, self.results_folder / 'merged_results')
                    else:
                        shutil.move(file, self.results_folder / 'merged_results')

        # Copy -domain.h5 file


        if postprocess:
            domain_folder = list(self.studies.values())[0].output_folder / 'input_files'
            domain_file = list(domain_folder.glob('*-domain.h5'))[0]
            shutil.copy(domain_file, self.results_folder / 'merged_results')
            logger.info('Postprocessing results')
            pflotran_postprocesser = PflotranPostprocessing()
            # Change the working directory to the results folder
            os.chdir(self.results_folder / 'merged_results')
            pflotran_postprocesser.run()
            # Return to the original working directory












