from typing import TYPE_CHECKING
import logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_component import ComsolComponent

class ComsolGeometry:
    def __init__(self,
                    comp: 'ComsolComponent',
                    tag: str = 'geom1'):
        """
        A class to handle the COMSOL geometry.
        Parameters:
            comp (ComsolComponent): The ComsolComponent object where the geometry lives.
            tag (str): The tag of the geometry. Defaults to 'geom1'.
        """
        self.comp = comp
        self.comsol = self.comp.comsol
        self.manager = self.comsol.manager
        self.model = self.comsol.model
        self.tag = tag
        self._api = self.comp._api.geom()
        self.childs = []

        if self.tag not in self.comp.get_childs():
            self.comp.childs.append(self)
        
        self.comp.geom = self
        
        logger.info(f"Geometry {self.tag} loaded.")

    def apply(self):
        #!TODO: To be implemented
        pass

    def get_childs(self):
        """
        Get the tags of the loaded childs of the ComsolGeometry
        """
        tags = []
        for child in self.childs:
            tags.append(child.tag)
        return tags
