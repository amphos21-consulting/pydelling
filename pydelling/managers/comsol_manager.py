from pathlib import Path
from pydelling.utils import create_results_folder
import logging
import mph
import time, re
import threading
from tqdm import tqdm
from shutil import copyfile
logger = logging.getLogger(__name__)

class ComsolManager:
    """
    A class to manage and run several COMSOL simulations using the COMSOL API for Python (mph).

    Warning: A valid COMSOL installation is required to use this class as well as java 11 or higher. Moreover, the oficial version of python is recommended, since the Microsoft Store version could cause issues with the COMSOL API.

    """
    def __init__(self,
                 version: str | None = None,
                 ):
        """
        Initialize the ComsolManager.

        Args:
            version (str | None): The version of COMSOL installed. If None, the latest version will be used.
        """
        self.client = mph.start(version=version)

        

    class ComsolModel:
        """
        A class representing a COMSOL model with all necessary information to run a simulation.
        """

        def __init__(self, 
                     file_path:  str, 
                     study: str | list, 
                     parameter_type: str = 'param',
                     parameter: str = None,
                     parameter_value: float = None,
                     variable_tag: str = None,
                     save_name: str = None,
                     ):
            """
            Initialize the Comsol Model.

            Args:
                file_path (str): Path to the COMSOL model file (.mph).
                study (str): The study tag to be run in the COMSOL model, pr a list of studies to be run in sequence.
                parameter_type (str, optional): The type of parameter to be modified before running the study. Options are 'param' for global parameters or 'var' for variables. Defaults to 'param'.
                parameter (str, optional): The parameter tag to be modified before running the study. If not provided, no parameter will be modified. Defaults to None.
                parameter_value (str, optional): The value (and units if needed) as a string to set for the specified parameter. Required if parameter is provided. Defaults to None.
                variable_tag (str, optional): The variable tag to be modified before running the study. Required if parameter_type is 'var'. Defaults to None.
                save_name (str, optional): The name to save the results file. If not provided the original file will be overwritten. Defaults to None.
            """
            self.file_path = file_path
            self.study = study
            self.parameter_type = parameter_type
            self.parameter = parameter
            self.parameter_value = parameter_value
            self.variable_tag = variable_tag
            self.save_name = save_name
            

    def run_batch(self,
                  models: list[ComsolModel],
                  ):
        """
        Run a batch of different COMSOL files.
        Args:
            models (list[Model]): A list of ComsolModel instances representing the COMSOL models to be run.
        """

        self.models_dict = models
        self._load_models()
        # self._run_parallel()
        self._run_in_series()
        self._clean()

    def run_parametric_sweep(self,
                             models: list[ComsolModel],
                             ):
        """
        Run a parametric sweep for a list of COMSOL models.
        A parameter must be defined in the ComsolModel class
        Args:
            models (list[Model]): A list of ComsolModel instances representing the COMSOL models to be run. If ComsolModel.save_name is not defined, an automatic name will be generated.
        """

        self.models_dict = models
        for model in self.models_dict:
            if model.save_name is None:
                model.save_name = model.file_path.split('.mph')[0] + f'_{model.parameter}_{model.parameter_value}.mph'
            copyfile(model.file_path, model.save_name)
            model.file_path = model.save_name

        
        self._load_models()

        for i in range(len(self.models_dict)):
            if model.parameter_type is 'param':
                self.models[i].param().set(self.models_dict[i].parameter, self.models_dict[i].parameter_value)
            if model.parameter_type is 'var':
                self.models[i].variable(self.models_dict[i].variable_tag).set(self.models_dict[i].parameter, self.models_dict[i].parameter_value)
            else:
                raise ValueError("parameter_type must be 'param' or 'var'")

        # self._run_parallel()
        self._run_in_series()
        self._clean()

    def run(self,
            model_dict: ComsolModel,
            ):
        """
        Run a single COMSOL model.
        Args:
            model_dict (ComsolModel): A ComsolModel instance representing the COMSOL model to be run.
        """
        self.models_dict = [model_dict]
        self.comsol_models = [self.client.load(self.models_dict[0].file_path)]
        self.models = [self.comsol_models[0].java]
        self.threads = [None]
        self._run_model()
        self._clean()

    def run_sequence_studies(self,
                             model_dict: ComsolModel,):
        """
        Run a sequence of studies in a COMSOL Model.
        Args:
            model_dict (ComsolModel): A ComsolModel instance representing the COMSOL model to be run.
        """
        self.models_dict = [model_dict]
        self.comsol_models = [self.client.load(self.models_dict[0].file_path)]
        self.models = [self.comsol_models[0].java]
        self.threads = [None]
        logger.info(f"Running model '{self.models_dict[0].file_path}'")
        self._run_studies(0)
        self._clean()
        



    def _load_models(self,
                     ):
        self.comsol_models = []
        self.models = []
        self.threads = []
        for i in range(len(self.models_dict)):
            self.comsol_models.append(self.client.load(self.models_dict[i].file_path))
            self.models.append(self.comsol_models[i].java)
            self.threads.append(None)

    def _run_modelutil(self,
                       model_index: int = 0):
        """
        Run a study of a COMSOL model reading COMSOL log, showing a progress bar.
        Args:
            model (mph.model.java): The COMSOL model object loaded in the client.
            model_index (int): The index of the ComsolModel instance in self.models_dict to be run.
        """
        logfile = Path(f"./logs/temp_{self.models_dict[model_index].file_path}_{int(time.time())}.log")
        if logfile.exists():
            logfile.unlink()
        

        from com.comsol.model.util import ModelUtil
        ModelUtil.showProgress(str(logfile))

        def run(model, study):
            model.study(study).run()
        
        # Read COMSOL log file to show progress bar
        self.threads[model_index] = threading.Thread(target=run, args=(self.models[model_index], self.models_dict[model_index].study))
        self.threads[model_index].start()

        pat = re.compile(r"Current Progress:\s+(\d+)\s*%")

        with tqdm(total=100, desc=f"     Running {self.models_dict[model_index].file_path}/{self.models_dict[model_index].study}", unit="%") as pbar:
            last = 0
            while self.threads[model_index].is_alive() or logfile.exists() or last < 100:
                if logfile.exists():
                    with logfile.open(encoding="utf-8") as f:
                        for line in f:
                            m = pat.search(line)

                            if m:
                                pct = int(m.group(1))
                                if pct > last:
                                    pbar.update(pct - last)
                                    last = pct              

                if not self.threads[model_index].is_alive() and last >= 100:
                    break
                time.sleep(0.1)
        self.threads[model_index].join()



    def _run_model(self,
                   model_index: int = 0,
                   ):
        """
        Run a single COMSOL model using the provided client.

        Args:
            model_index (int): The index of the ComsolModel instance in self.models_dict to be run.
        """
        # Run the specified study
        try:
            logger.info(f"Running model '{self.models_dict[model_index].file_path}'")
            # self.models[model_index].study(self.models_dict[model_index].study).run()
            self._run_modelutil(model_index)
        except Exception as e:
            logger.error(f"Error running study '{self.models_dict[model_index].study}' in model '{self.models_dict[model_index].file_path}': {e}")
        

        # Save the results
        if self.models_dict[model_index].save_name:
            self.models[model_index].save(str(self.models_dict[model_index].save_name))
            logger.info(f"Model '{self.models_dict[model_index].save_name}' completed and saved.")
        else:
            self.models[model_index].save(str(self.models_dict[model_index].file_path))
            logger.info(f"Model '{self.models_dict[model_index].file_path}' completed and saved.")

        return 0

    def _run_parallel(self,
                      ):
        """
        Run COMSOL models in parallel.
        Warning: This method is currently disabled due to mph API does not allow it and it waits to a process to end before starting the next one, even in independent threads.
        Use _run_in_series instead.
        """
        # class Thread:
        #     def __init__(self,
        #                  t: threading.Thread,
        #                  client_id: int):
        #         self.t = t
        #         self.client_id = client_id

        # threads = []
        # thread_client = []
        # n_models = len(self.models_dict)
        # n_runs = 0
        
        # status1 = False
        # status2 = False
    
        # i = 0
        # # Maximum 2 clients simultaneously
        # with tqdm(total=n_models, desc="Running COMSOL simulations") as pbar:
        #     while i < n_models or n_runs > 0:
        #         while n_runs < 2 and i < n_models:
        #             if not status1:
        #                 t = threading.Thread(target=self._run_model, args=([i]))
        #                 tclass = Thread(t, 1)
        #                 status1 = True
        #                 t.start()
        #                 threads.append(tclass)
        #                 i += 1
        #                 n_runs += 1
        #             time.sleep(0.1)
                    
        #             if not status2:
        #                 t = threading.Thread(target=self._run_model, args=([i]))
        #                 tclass = Thread(t, 2)
        #                 status2 = True
        #                 t.start()
        #                 threads.append(tclass)
        #                 i += 1
        #                 n_runs += 1

        #         for t in threads[:]:
        #             if not t.t.is_alive():
        #                 if t.client_id == 1:
        #                     status1 = False
        #                 if t.client_id == 2:
        #                     status2 = False
        #                 threads.remove(t)
        #                 n_runs -= 1
                        
        #                 pbar.update(1)
        #                 time.sleep(0.1)
        #         time.sleep(0.1)
        # for t in threads[:]:
        #     t.t.join()
        logger.error("Parallel execution is currently disabled. Use _run_in_series instead.")

    def _run_in_series(self,
                       ):
        """
        Run COMSOL models in series.
        """
        for i in tqdm(range(len(self.models_dict)),desc="Running COMSOL simulations"):
            self._run_model(i)

    def _run_studies(self,
                   model_index: int, 
                    ):
        """
        Run a study of a COMSOL model using the provided client.

        Args:
            model_index (int): The index of the ComsolModel instance in self.models_dict to be run.
        """
        # Run the specified study
        for s in range(len(self.models_dict[model_index].study)):
            try:
                logger.info(f"Running study '{self.models_dict[model_index].study[s]}'")
                self._run_modelutil(self.models[model_index], self.models_dict[model_index].file_path, self.models_dict[model_index].study[s])
                # Save the results
                logger.info(f"Study '{self.models_dict[model_index].study[s]}' completed. Saving results...")
                if self.models_dict[model_index].save_name:
                    self.models[model_index].save(str(self.models_dict[model_index].save_name))
                else:
                    self.models[model_index].save(str(self.models_dict[model_index].file_path))

            except Exception as e:
                logger.error(f"Error running study '{self.models_dict[model_index].study[s]}' in model '{self.models_dict[model_index].file_path}': {e}")
        
        
        logger.info(f"Model '{self.models_dict[model_index].file_path}' completed and saved.")
        return 0

    def _clean(self):
        """
        Clean temporary log files except the last one.
        """
        
        time.sleep(0.1)
        for logfile in Path('./logs/').glob('temp_*.log'):
            try:
                logfile.unlink()
            except PermissionError:
                pass