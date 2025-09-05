from pathlib import Path
from pydelling.utils import create_results_folder
import logging
import mph
import threading
import time
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
                     study: str, 
                     parameter: str = None,
                     parameter_value: float = None,
                     save_name: str = None,
                     ):
            """
            Initialize the Comsol Model.

            Args:
                file_path (str): Path to the COMSOL model file (.mph).
                study (str): The study tag to be run in the COMSOL model.
                parameter (str, optional): The parameter tag to be modified before running the study. If not provided, no parameter will be modified. Defaults to None.
                parameter_value (float, optional): The value to set for the specified parameter. Required if parameter is provided. Defaults to None.
                save_name (str, optional): The name to save the results file. If not provided the original file will be overwritten. Defaults to None.
            """
            self.file_path = file_path
            self.study = study
            self.parameter = parameter
            self.parameter_value = parameter_value
            self.save_name = save_name
            


    def run_batch(self,
                  models: list[ComsolModel],
                  ):
        """
        Run a batch of different COMSOL files.
        Args:
            models (list[Model]): A list of Model instances representing the COMSOL models to be run.
        """

        def _run_model(self,
                       input_model: 'ComsolManager.ComsolModel', 
                       comsol_model: mph.model):
            """
            Run a single COMSOL model using the provided client.

            Args:
                input_model (ComsolModel): The Model instance representing the COMSOL model to be run.
                comsol_model (mph.model): The COMSOL model object loaded in the client.
            """
            # Load the COMSOL model
            model = comsol_model.java

            # # Set parameter if provided
            # if model.parameter and model.parameter_value is not None:
            #     comsol_model.param.set(model.parameter, model.parameter_value)

            # Run the specified study
            try:
                logger.info(f"Running model '{input_model.file_path}'")
                model.study(input_model.study).run()
            except Exception as e:
                logger.error(f"Error running study '{input_model.study}' in model '{input_model.file_path}': {e}")
            

            # Save the results
            if input_model.save_name:
                model.save(str(input_model.save_name))
            else:
                model.save(str(input_model.file_path))

            return 0

        class Thread:
            def __init__(self,
                         t: threading.Thread,
                         client_id: int):
                self.t = t
                self.client_id = client_id
    
        threads = []
        thread_client = []
        n_models = len(models)
        n_runs = 0
        
        status1 = False
        status2 = False
    
        comsol_models = []
        for i in range(n_models):
            comsol_models.append(self.client.load(models[i].file_path))
        
        i = 0
        # Maximum 2 clients simultaneously
        with tqdm(total=n_models, desc="Running COMSOL simulations") as pbar:
            while i < n_models or n_runs > 0:
                while n_runs < 2 and i < n_models:
                    if not status1:
                        t = threading.Thread(target=_run_model, args=(self, models[i], comsol_models[i]))
                        tclass = Thread(t, 1)
                        status1 = True
                        t.start()
                        threads.append(tclass)
                        i += 1
                        n_runs += 1
                    time.sleep(0.1)
                    
                    if not status2:
                        t = threading.Thread(target=_run_model, args=(self, models[i], comsol_models[i]))
                        tclass = Thread(t, 2)
                        status2 = True
                        t.start()
                        threads.append(tclass)
                        i += 1
                        n_runs += 1

                for t in threads[:]:
                    if not t.t.is_alive():
                        if t.client_id == 1:
                            status1 = False
                        if t.client_id == 2:
                            status2 = False
                        threads.remove(t)
                        n_runs -= 1
                        
                        pbar.update(1)
                        time.sleep(0.1)
                time.sleep(0.1)


        