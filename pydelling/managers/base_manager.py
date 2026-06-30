"""This class is the base class for all simulation managers. A simulation manager should be able to:
- Manage study [BaseStudy] objects
- Run simulations on a given software
- Read the output status of the simulation
"""

from .base_study import BaseStudy
from abc import ABC, abstractmethod
from typing import Dict, List, Union
import logging
from alive_progress import alive_bar
from tqdm import tqdm
from pydelling.utils import create_results_folder
from pydelling.managers.ssh import BaseSsh, JurecaSsh, LumiSsh
from docker import DockerClient
from pathlib import Path
import subprocess


logger = logging.getLogger(__name__)


class BaseManager(ABC):
    """Abstract manager for orchestrating simulation studies and execution backends.

    Category: Simulation management.
    Tags: studies, execution, docker, hpc, ssh, callbacks.
    Use when: to understand how pydelling batches
        ``BaseStudy`` instances, writes run files, and dispatches simulations to
        local, Docker, or remote HPC backends.
    """

    def __init__(self, name: str = None):
        """
        Initialize manager state and common runtime attributes.
        
        Args:
            name (str): Description.
        """
        self.results_folder = None
        self.studies: Dict[str, BaseStudy] = {}
        self.manager_name = name if name is not None else self.__class__.__name__
        self.is_dummy = False
        self.ssh: BaseSsh = None
        self.password = None


    def add_study(self, study: BaseStudy):
        """Register a study in the manager by its ``study.name``.

        Category: Simulation management.
        Tags: studies, registry, base-study.
        Use when: building a batch of simulations before calling ``run`` or
            ``generate_run_files``.
        Args:
            study: ``BaseStudy`` instance to add to the manager.
        Raises:
            AssertionError: If ``study`` is not a ``BaseStudy`` instance.
        Side effects:
            Stores the study in ``self.studies`` keyed by name.
        """
        assert isinstance(study, BaseStudy), f"Study must be a object from a class inherited from BaseStudy, not {type(study)}"
        self.studies[study.name] = study

    def run(self,
            studies_folder: str = './studies',
            n_cores: int = 1,
            docker_image: str = None,
            dummy: bool = False,
            start_from: int = None,
            petsc_dir: str = '/opt/pflotran-dev/petsc',
            petsc_arch: str = 'arch-linux-c-opt',
            pflotran_dir: str = 'pflotran',
            pre_commands: List[str] = None,
            run_on: str = None,
            user: str = None,
            project_name: str = None,
            pkey_path: str = None,
            wallclock_limit: float = 23,
            shell_script: str = None,
            download_file_extensions: List[str] = None,
            download_results: bool = True,
            password: str = None,
            **kwargs,
            ):
        """Run every registered study through the selected execution backend.

        Category: Simulation management.
        Tags: studies, execution, docker, jureca, lumi, callbacks.
        Use when: an MCP workflow has a populated manager and needs to create
            result folders, initialize study callbacks, run optional setup
            commands, and dispatch each study.
        Args:
            studies_folder: Base directory where timestamped result folders are
                created.
            n_cores: Number of CPU cores requested for each study.
            docker_image: Docker image name for container execution. When
                provided and ``run_on`` is not a remote platform, studies are
                routed through ``_run_study_docker``.
            dummy: If ``True``, write study files without executing solvers.
            start_from: One-based study index from which real execution starts;
                earlier studies are written in dummy mode.
            petsc_dir: PETSc installation path forwarded to concrete PFLOTRAN
                managers.
            petsc_arch: PETSc architecture name forwarded to concrete managers.
            pflotran_dir: PFLOTRAN executable or installation selector passed to
                concrete managers.
            pre_commands: Shell commands executed before iterating studies.
            run_on: Remote platform selector. Supported values here are
                ``"jureca"`` and ``"lumi"``.
            user: Remote user for HPC execution.
            project_name: Remote allocation or project name for HPC execution.
            pkey_path: Path to the SSH private key for remote execution.
            wallclock_limit: Wallclock limit in hours for remote jobs.
            shell_script: Optional shell script used by remote runners.
            download_file_extensions: Result file extensions to download from
                remote runs.
            download_results: Whether remote runs should download results.
            password: Optional password forwarded to SSH helpers.
            **kwargs: Extra backend-specific parameters passed to
                ``run_study`` and concrete manager implementations.
        Side effects:
            Creates ``self.results_folder``, may run shell commands, writes
            study files, starts simulations, and may configure SSH state.
        """
        # Set ssh
        if run_on in ['jureca', 'lumi']:
            self.set_ssh(user=user, pkey_path=pkey_path, project_name=project_name, password=password, platform=run_on)
            self.on_remote = True
        else:
            self.on_remote = False

        self.is_dummy = dummy
        shell_script = Path(shell_script).absolute() if shell_script is not None else None
        self.password = password
        # Initialize callbacks
        for study in self.studies.values():
            study.initialize_callbacks(self)

        self.results_folder = create_results_folder(studies_folder)
        self.studies_folder_name = Path(studies_folder).name
        # self.generate_run_files(studies_folder=studies_folder)
        # Run the precommands if any
        if pre_commands is not None:
            for command in pre_commands:
                logger.info(f"Running precommand: {command}")
                subprocess.run(command, shell=True)
        for study in tqdm(self.studies.values(), desc="Running studies", colour="white"):
            study: BaseStudy
            if start_from is not None:
                if study.idx < start_from - 1:
                    logger.info(
                        f"Skipping study {study.name} (idx: {study.idx}) because start_from is set to {start_from}")
                    self.run_study(study,
                                   docker_image=docker_image,
                                   n_cores=n_cores,
                                   dummy=True,
                                   petsc_dir=petsc_dir,
                                   petsc_arch=petsc_arch,
                                   pflotran_dir=pflotran_dir,
                                   run_on=run_on,
                                   user=user,
                                   project_name=project_name,
                                   pkey_path=pkey_path,
                                   wallclock_limit=wallclock_limit,
                                   shell_script_path=shell_script,
                                   download_file_extensions=download_file_extensions,
                                   download_results=download_results,
                                   **kwargs)
                    continue
            self.run_study(study,
                           docker_image=docker_image,
                           n_cores=n_cores,
                           dummy=dummy,
                           petsc_dir=petsc_dir,
                           petsc_arch=petsc_arch,
                           pflotran_dir=pflotran_dir,
                           run_on=run_on,
                           user=user,
                           project_name=project_name,
                           pkey_path=pkey_path,
                           wallclock_limit=wallclock_limit,
                           shell_script_path=shell_script,
                           download_file_extensions=download_file_extensions,
                           download_results=download_results,
                           **kwargs)

    def generate_run_files(self, studies_folder: str = './studies'):
        """Write input files for all registered studies without dispatching them.

        Category: Simulation management.
        Tags: studies, file-generation, dry-run.
        Use when: to write reproducible solver input decks on disk but
            should not launch the solver.
        Args:
            studies_folder: Kept for API compatibility; run files are written
                under ``self.results_folder``.
        Side effects:
            Calls ``study.to_file`` for each registered study.
        """
        for study in self.studies.values():
            study: BaseStudy
            study.to_file(self.results_folder / study.name)

    @abstractmethod
    def _run_study(self, study: BaseStudy, n_cores: int = 1, **kwargs):
        """
        This method runs a study.
        
        Args:
            study (BaseStudy): Description.
            n_cores (int): Description.
            **kwargs (Any): Description.
        """
        logger.info(f"Running study {study.name}")
        return NotImplementedError("This method must be implemented in the child class")

    @abstractmethod
    def _run_study_docker(self,
                          study: BaseStudy,
                          docker_image: str,
                          n_cores: int = 1,
                          **kwargs,
                          ):
        """
        This method runs a study using docker.
        
        Args:
            study (BaseStudy): Description.
            docker_image (str): Description.
            n_cores (int): Description.
            **kwargs (Any): Description.
        """
        logger.info(f"Running study {study.name} using docker image {docker_image}")
        return NotImplementedError("This method must be implemented in the child class")

    def _run_study_jureca(self,
                            study: BaseStudy,
                            user: str,
                            project_name: str,
                            pkey_path: str,
                            n_cores: int = 1,
                            wallclock_limit: float = None,
                            shell_script: str = None,
                            download_results: bool = True,
                            **kwargs,
                            ):
        """
        This method runs a study in JURECA.
        
        Args:
            study (BaseStudy): Description.
            user (str): Description.
            project_name (str): Description.
            pkey_path (str): Description.
            n_cores (int): Description.
            wallclock_limit (float): Description.
            shell_script (str): Description.
            download_results (bool): Description.
            **kwargs (Any): Description.
        """
        logger.info(f"Running study {study.name} in JURECA")
        return NotImplementedError("This method must be implemented in the child class")

    def _run_study_lumi(self,
                            study: BaseStudy,
                            user: str,
                            project_name: str,
                            pkey_path: str,
                            n_cores: int = 1,
                            wallclock_limit: float = None,
                            shell_script: str = None,
                            download_results: bool = True,
                            **kwargs,
                            ):
        """
        This method runs a study in LUMI supercomputer.
        
        Args:
            study (BaseStudy): Description.
            user (str): Description.
            project_name (str): Description.
            pkey_path (str): Description.
            n_cores (int): Description.
            wallclock_limit (float): Description.
            shell_script (str): Description.
            download_results (bool): Description.
            **kwargs (Any): Description.
        """
        logger.info(f"Running study {study.name} in LUMI")
        return NotImplementedError("This method must be implemented in the child class")

    def run_study(self,
                  study: BaseStudy,
                  n_cores: int = 1,
                  docker_image: str = None,
                  run_on: str = None,
                  dummy: bool = False,
                  user: str = None,
                  project_name: str = None,
                  pkey_path: str = None,
                  wallclock_limit: float = 23,
                  shell_script: str = None,
                  download_file_extensions: List[str] = None,
                  download_results: bool = True,
                  **kwargs,
                  ):
        """Write and execute one study with callbacks and post-processing.

        Category: Simulation management.
        Tags: study, execution, callbacks, docker, hpc.
        Use when: to understand the per-study execution path used by
            ``run`` or wants to understand how manager backends are selected.
        Args:
            study: Study instance to write and execute.
            n_cores: Number of CPU cores requested for execution.
            docker_image: Docker image used when dispatching through Docker.
            run_on: Remote platform selector, currently ``"jureca"`` or
                ``"lumi"`` for built-in SSH helpers.
            dummy: If ``True``, only writes the study files.
            user: Remote username for HPC execution.
            project_name: Remote project or allocation name.
            pkey_path: SSH private key path for remote execution.
            wallclock_limit: Wallclock limit in hours for remote jobs.
            shell_script: Optional script passed to remote execution helpers.
            download_file_extensions: Remote result extensions to retrieve.
            download_results: Whether remote execution should retrieve results.
            **kwargs: Additional concrete backend parameters.
        Side effects:
            Sets ``study.output_folder``, runs pre/post callbacks, writes files,
            calls one concrete execution method, and invokes ``study.post_run``.
        """
        logger.info(f"Running study {study.name}")
        # Create the study files
        study.output_folder = self.results_folder / study.name
        if dummy:
            logger.info("Dummy run, not running the study")
            study.to_file(self.results_folder / study.name)
        else:
            for callback in study.callbacks:
                if callback.kind == 'pre':
                    callback.run(self.on_remote)
            study.to_file(self.results_folder / study.name)

            # Run the study
            if run_on == 'jureca':
                self._run_study_jureca(study,
                                       n_cores=n_cores,
                                       user=user,
                                       project_name=project_name,
                                       pkey_path=pkey_path,
                                       wallclock_limit=wallclock_limit,
                                       shell_script=shell_script,
                                       download_file_extensions=download_file_extensions,
                                       download_results=download_results,
                                       **kwargs)
            elif run_on == 'lumi':
                self._run_study_lumi(study,
                                     n_cores=n_cores,
                                     user=user,
                                     project_name=project_name,
                                     pkey_path=pkey_path,
                                     wallclock_limit=wallclock_limit,
                                     shell_script=shell_script,
                                     download_file_extensions=download_file_extensions,
                                     download_results=download_results,
                                     **kwargs)
            elif docker_image is not None:
                self._run_study_docker(study, docker_image, n_cores=n_cores, **kwargs)
            else:
                self._run_study(study, n_cores=n_cores, **kwargs)
            for step in study.steps:
                if step.kind == 'post':
                    step.run()
            for callback in study.callbacks:
                if callback.kind == 'post':
                    callback.run(self.on_remote)

            study.post_run()

    def set_ssh(self,
                platform: str,
                user: str,
                pkey_path: str,
                project_name: str,
                password: str = None,
                **kwargs,
                ):
        """Attach the SSH helper for a supported remote platform.

        Category: Simulation management.
        Tags: ssh, hpc, jureca, lumi, remote-execution.
        Use when: a manager is preparing to run studies on a configured HPC
            backend rather than locally or in Docker.
        Args:
            platform: Remote platform key. Supported values are ``"jureca"`` and
                ``"lumi"``.
            user: Remote username.
            pkey_path: Path to an SSH private key.
            project_name: Remote allocation or project name.
            password: Optional SSH password.
            **kwargs: Extra constructor parameters forwarded to the SSH helper.
        Side effects:
            Instantiates and stores ``self.ssh``.
        """
        platform_to_ssh = {
            'jureca': JurecaSsh,
            'lumi': LumiSsh,
        }
        func_kwargs = {'user': user,
                'pkey_path': pkey_path,
                'password': password,
                'project_name': project_name,
                }
        func_kwargs.update(kwargs)
        self.ssh: BaseSsh = platform_to_ssh[platform](**func_kwargs)


    @property
    def n_studies(self):
        """This method returns the number of studies.
        """
        return len(self.studies)

    def merge_studies(self):
        """This methods merges the studies generated by the manager.
        """
        pass
