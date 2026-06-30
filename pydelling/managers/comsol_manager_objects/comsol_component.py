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
    """Wrapper around a COMSOL component API object.

    Category: COMSOL management.
    Tags: comsol, component, geometry, variables, model-input.
    Use when: an MCP agent needs to discover how pydelling accesses component
        geometry, variables, and model inputs through the COMSOL Java API.
    """

    def __init__(self,
                 comsol: 'ComsolManager.ComsolModel',
                 tag: str):
        """Load a COMSOL component by tag.

        Category: COMSOL management.
        Tags: comsol, component, initialization.
        Use when: attaching pydelling helpers to an existing COMSOL component.
        Parameters:
            comsol (ComsolModel): The ComsolModel object from ComsolManager
            tag (str): The tag of the component
        Side effects:
            Registers the component as a child, stores the COMSOL API object, and
            initializes the default geometry wrapper.
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
        """Placeholder for applying component changes.

        Category: COMSOL management.
        Tags: comsol, component, apply, extension-point.
        Use when: extending component wrappers with explicit apply behavior.
        """
        pass

    def geometry(self, tag: str = 'geom1'):
        """Return a geometry wrapper for this component.

        Category: COMSOL management.
        Tags: comsol, component, geometry.
        Use when: accessing or creating geometry operations under a component.
        Parameters:
            tag (str): The tag of the component
        Returns:
            ComsolGeometry: Wrapper for the component geometry.
        """
        return ComsolGeometry(self, tag)
    
    def variables(self,
                  tag: str | None = None):
        """Return a component-scoped variable collection wrapper.

        Category: COMSOL management.
        Tags: comsol, variables, component.
        Use when: reading or setting variables that live inside this component.
        Parameters:
            tag (str): The tag of the variable collection. If None, a new variable collection will be created. Defaults to None.
        Returns:
            ComsolVariables: Variable collection wrapper bound to this component.
        """
        return ComsolVariables(self, tag, True)

    def change_model_input(self,
                        model_input_tag: str,
                        expression: str):
        """Change a COMSOL model input expression for this component.

        Category: COMSOL management.
        Tags: comsol, model-input, expression, component.
        Use when: updating a component model input such as ``minput.pA``.
        Parameters:
            model_input_tag (str): The tag of the model input, i.e. minput.pA
            expression (str): The expression to set in the model input.
        Side effects:
            Calls the COMSOL API ``set`` method on the selected common input.
        """
        self._api.common(model_input_tag).set('minpScalar', expression)        

    def get_childs(self):
        """Return tags for wrappers loaded under this component.

        Category: COMSOL management.
        Tags: comsol, component, children.
        Use when: checking whether geometry or variable wrappers are already
            registered under the component.
        Returns:
            list: Child wrapper tags.
        """
        tags = []
        for child in self.childs:
            tags.append(child.tag)
        return tags
