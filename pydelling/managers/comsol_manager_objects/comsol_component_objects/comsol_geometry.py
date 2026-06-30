from typing import TYPE_CHECKING
import logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_component import ComsolComponent

class ComsolGeometry:
    """Wrapper around a COMSOL component geometry API object.

    Category: COMSOL management.
    Tags: comsol, geometry, component, children.
    Usage: to access geometry operations under a COMSOL
        component through pydelling.
    """

    def __init__(self,
                    comp: 'ComsolComponent',
                    tag: str = 'geom1'):
        """Load a COMSOL geometry by component and tag.

        Category: COMSOL management.
        Tags: comsol, geometry, initialization.
        Usage: attaching pydelling helpers to a component geometry.
        Parameters:
            comp (ComsolComponent): The ComsolComponent object where the geometry lives.
            tag (str): The tag of the geometry. Defaults to 'geom1'.
        Side effects:
            Registers this geometry wrapper under the component and assigns it as
            ``comp.geom``.
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
        """Placeholder for applying geometry changes.

        Category: COMSOL management.
        Tags: comsol, geometry, apply, extension-point.
        Usage: extending geometry wrappers with explicit apply behavior.
        """
        pass

    def get_childs(self):
        """Return tags for wrappers loaded under this geometry.

        Category: COMSOL management.
        Tags: comsol, geometry, children.
        Usage: checking whether geometry child wrappers are already
            registered.
        Returns:
            list: Child wrapper tags.
        """
        tags = []
        for child in self.childs:
            tags.append(child.tag)
        return tags
