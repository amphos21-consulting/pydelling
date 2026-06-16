"""
A class to manage and run several COMSOL simulations using the COMSOL API for Python (mph).

Warning: A valid COMSOL installation is required to use this class as well as java 11 or higher. Moreover, the oficial version of python is recommended, since the Microsoft Store version could cause issues with the COMSOL API.

"""

from pathlib import Path
from pydelling.utils import create_results_folder
import logging
import mph
import time, re
from tqdm import tqdm
from shutil import copyfile
from pathlib import Path
import jpype

from .comsol_manager_objects.comsol_results import ComsolResults
from .comsol_manager_objects.comsol_study import ComsolStudy
from .comsol_manager_objects.comsol_component import ComsolComponent
from .comsol_manager_objects.comsol_variables_and_parameters import ComsolVariables, ComsolParameters

logger = logging.getLogger(__name__)

class ComsolManager:
    def __init__(self,
                 version: str | None = None,
                 ):
        """
        Initialize the ComsolManager.
        Warning: A valid COMSOL installation is required to use this class as well as java 11 or higher. Moreover, the oficial version of python is recommended, since the Microsoft Store version could cause issues with the COMSOL API.

        Parameters:
            version (str or bool): The version of COMSOL to use. If False, the default version is used.
        """
        self.client = mph.start(version=version)
        self.childs = []


    class ComsolModel:
        """
        A class representing a COMSOL model with all necessary information to run a simulation.
        """

        def __init__(self,
                     manager: "ComsolManager",
                     file_path:  str, 
                     study: str | list | None = None, 
                     parameter_type: str = 'param',
                     parameter: str = None,
                     parameter_value: float = None,
                     variable_tag: str = None,
                     save_name: str | None = None,
                     model_input: list = None,
                     model_input_value: list = None,
                     ):
            """
            Initialize the Comsol Model.

            Args:
                manager (ComsolManager): The ComsolManager object.
                file_path (str): Path to the COMSOL model file (.mph).
                study (str): The study tag to be run in the COMSOL model, pr a list of studies to be run in sequence.
                parameter_type (str, optional): The type of parameter to be modified before running the study. Options are 'param' for global parameters or 'var' for variables. Defaults to 'param'.
                parameter (str, optional): The parameter tag to be modified before running the study. If not provided, no parameter will be modified. Defaults to None.
                parameter_value (str, optional): The value (and units if needed) as a string to set for the specified parameter. Required if parameter is provided. Defaults to None.
                variable_tag (str, optional): The variable tag to be modified before running the study. Required if parameter_type is 'var'. Defaults to None.
                save_name (str, optional): The name to save the results file. If not provided the original file will be overwritten. Defaults to None.
                model_input (list, optional): A list with two elements: [component_tag, modelinput_tag] to set a Model Input before running the study. If not provided, no Model Input will be modified. Defaults to None. Only used in run_sequence_studies.
                model_input_value (list, optional): A list of values (and units if needed). Defaults to None. Only used in run_sequence_studies.
            """
            self.manager = manager
            self.file_path = file_path
            self.model_standalone = self.manager.client.load(file_path)
            self.model = self.model_standalone.java
            self._api = self.model
            self.results = self._results()
            self.childs = [self.results]
            self.studies = []

            if study is not None: self._study(study)
            
            self.parameter_type = parameter_type
            self.parameter = parameter
            self.parameter_value = parameter_value
            self.variable_tag = variable_tag
            self.save_name = save_name
            self.model_input = model_input
            self.model_input_value = model_input_value

            if self.file_path not in [child.file_path for child in self.manager.childs]:
                self.manager.childs.append(self)
                logger.info(f"COMSOL model {Path(self.file_path).name} loaded.")
            else: logger.info(f"COMSOL model {Path(self.file_path).name} loaded but already in ComsolManager childs.")

        def _results(self):
            """
            Initializes a class to handle COMSOL results.
            Returns a ComsolResults class
            """
            return ComsolResults(self)
            
        def _study(self, tag: str):
            """
            Initializes a class to handel COMSOL studies.
            Parameters:
                tag (str): The tag of the study
            """
            ComsolStudy(self, tag)
            
        def study(self, tag: str):
            """
            Initializes a class to handel COMSOL studies.
            Returns a ComsolStudy class
            Parameters:
                tag (str): The tag of the study
            """
            return ComsolStudy(self, tag)

        def get_childs(self):
            """
            Get the tags of the loaded childs of the ComsolComponent
            """
            tags = []
            for child in self.childs:
                tags.append(child.tag)
            return tags

        def get_studies(self):
            """
            Returns a list with the tags of the loaded studies.
            """
            tags = []
            for study in self.studies:
                tags.append(study.tag)
            return tags

        def component(self, tag):
            """
            Returns a class to handle a COMSOL component.
            Parameters:
                tag (str): The tag of the component
            """
            return ComsolComponent(self, tag)

        def variables(self,
                    tag: str | None = None):
            """
            A class to handle the COMSOL variable collection.
                Parameters:
                    tag (str): The tag of the variable collection. If None, a new variable collection will be created. Defaults to None.
            """
            return ComsolVariables(self, tag)
        
        def parameters(self):
            """
            A class to handle the COMSOL parameter collection.
            """
            return ComsolParameters(self)


        def apply(self):
            """
            Apply the changes of the ComsolManager childs to the COMSOL API model.
            """
            for child in self.childs:
                child.apply()

        def run_sequence(self,
                        studies: list,
                        comp: None = None,
                        minput_tag: str | None = None,
                        minput_value: list | None = None):
            """
            Runs a sequence of studies in a COMSOL model. Model Input can be changed if needed.
            Parameters:
                studies (list of ComsolStudy): the list of ComsolStudy's to be run.
                comp (ComsolComponent): If the model input has to be changes the ComsolComponent is needed. Defaults to None.
                minput_tag (str): The Model Input tag. Defaults to None.
                minput_value (list of str): The Model Input value. Defaults to None.
            """
            for i in tqdm(range(len(studies)), "Running sequence"):
                if comp is not None:
                    comp.change_model_input(minput_tag, minput_value[i])
                studies[i].run()

        def save(self, save_path: str | None = None):
            """
            Save the COMSOL model to a file.
            Parameters:
                save_path (str): The path to save the COMSOL model. If None, the original file path is overwritten.
            """
            if save_path is None:
                if self.save_name is not None:
                    save_path = self.save_name
                else: save_path = self.file_path
            logger.info(f"Saving COMSOL model to {save_path}")
            try: self.model.save(save_path)
            except:
                new_save_path = f"{Path(save_path).parent}/{Path(save_path).stem}_ComsolManager.mph"
                logger.warning(f"COMSOL file is locked. Model saved in {new_save_path}")
                self.model.save(new_save_path)
        
    def comsol_model(self,
                    file_path:  str, 
                    study: str | list | None = None, 
                    parameter_type: str = 'param',
                    parameter: str = None,
                    parameter_value: float = None,
                    variable_tag: str = None,
                    save_name: str = None,
                    model_input: list = None,
                    model_input_value: list = None,
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
                model_input (list, optional): A list with two elements: [component_tag, modelinput_tag] to set a Model Input before running the study. If not provided, no Model Input will be modified. Defaults to None. Only used in run_sequence_studies.
                model_input_value (list, optional): A list of values (and units if needed). Defaults to None. Only used in run_sequence_studies.
        """
        return self.ComsolModel(self,file_path,study,parameter_type,parameter,parameter_value,variable_tag,save_name,model_input,model_input_value)

    def run_batch(self,
                  studies: list[ComsolStudy],
                  ):
        """
        Run a batch of different COMSOL studies.
        Args:
            studies (list[ComsolStudy]): A list of ComsolStudy instances to be run.
        """

        for study in studies:
            study.run()


    def run_sequence_studies(self,
                             model_dict: ComsolModel,):
        """
        Run a sequence of studies in a COMSOL Model.
        model_dict.study must be a list of studies to be run in sequence.
        If Model Input must be changes provide model_dict.model_input=[component_tag, modelinput_tag] and model_dict.model_input_value a list of values
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
                if self.models_dict[model_index].model_input is not None:
                    self.models[model_index].component(self.models_dict[model_index].model_input[0]).common(self.models_dict[model_index].model_input[1]).set('minpScalar',self.models_dict[model_index].model_input_value[s])
                logger.info(f"Running study '{self.models_dict[model_index].study[s]}'")
                self._run_modelutil(model_index, s)
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

    def _clean_logs(self):
        """
        Clean temporary log files except the last one.
        """
        
        time.sleep(0.1)
        for logfile in Path('./logs/').glob('temp_*.log'):
            try:
                logfile.unlink()
            except PermissionError:
                pass

    def __java_str__(self, obj):
        return jpype.JString(obj)
    
    def __java_double__(self, obj):
        return jpype.JDouble(obj)
    
    def __java_int__(self, obj):
        return jpype.JInt(obj)
    
    def __java_matrix__(self, obj):
        pass
