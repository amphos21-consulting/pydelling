import logging
from typing import TYPE_CHECKING
from pathlib import Path
from tqdm import tqdm

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_manager import ComsolManager

from .comsol_component_objects.comsol_geometry import ComsolGeometry
from .comsol_variables_and_parameters import ComsolVariables

class ComsolComponent:
    def __init__(self,
                 comsol: 'ComsolManager.ComsolModel',
                 tag: str):
        """
        A class to handle a COMSOL component.
        Parameters:
            comsol (ComsolModel): The ComsolModel object from ComsolManager
            tag (str): The tag of the component
        """
        self.comsol = comsol
        self.manager = self.comsol.manager
        self.model = self.comsol.model
        self.tag = tag
        self._api = self.model.component(self.tag)
        self.childs = []
    
        if self.tag not in [study.tag for study in self.comsol.studies]:
            self.comsol.studies.append(self)
            self.comsol.childs.append(self)
    
        self.geom = self.geometry()

        logger.info(f"Study {self.tag} loaded.")


    def apply(self):
        #!TODO: To be implemented
        pass

    def geometry(self, tag: str = 'geom1'):
        """
        Returns a class to handle a COMSOL component.
        Parameters:
            tag (str): The tag of the component
        """
        return ComsolGeometry(self, tag)
    
    def variables(self,
                  tag: str | None = None):
        """
        A class to handle the COMSOL variable collection.
            Parameters:
                tag (str): The tag of the variable collection. If None, a new variable collection will be created. Defaults to None.
        """
        return ComsolVariables(self, tag, True)

    def change_model_input(self,
                        model_input_tag: str,
                        expression: str):
        """
        Change the model input of this component.
        Parameters:
            model_input_tag (str): The tag of the model input, i.e. minput.pA
            expression (str): The expression to set in the model input.
        """
        self._api.common(model_input_tag).set('minpScalar', expression)        

    def get_childs(self):
        """
        Get the tags of the loaded childs of the ComsolComponent
        """
        tags = []
        for child in self.childs:
            tags.append(child.tag)
        return tags