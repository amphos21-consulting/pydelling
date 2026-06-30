from typing import TYPE_CHECKING
import logging, re
import pandas as pd

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_manager import ComsolManager

class ComsolVariables:
    """Wrapper around a COMSOL variable collection.

    Category: COMSOL management.
    Tags: comsol, variables, component, dataframe.
    Use when: an MCP agent needs to set, list, or move COMSOL variable
        collections through pydelling.
    """

    def __init__(self,
                parent,
                tag: str | None = None,
                iscomp: bool = False):
        """Load or create a COMSOL variable collection.

        Category: COMSOL management.
        Tags: comsol, variables, initialization.
        Use when: accessing an existing variable collection or creating a new
            one globally or under a component.
        Parameters:
            parent (ComsolModel or ComsolComponent): The object where the variable lives.
            tag (str): The tag of the variable collection. If None, a new variable collection will be created. Defaults to None.
            iscomp (bool): True if the variable collection lives in a component. False if its global. Defaults to False.
        Side effects:
            Creates or loads the COMSOL variable API object and registers this
            wrapper under the model or component.
        """
        if not iscomp:
            self.comsol = parent
            self.comp = None
        else:
            self.comp = parent
            self.comsol = self.comp.comsol
        self.manager = self.comsol.manager
        self.model = self.comsol.model

        if tag is None:
            tags = self.model.variable().tags()
            try: last_tag = max([int(re.findall(r'\d+', str(temptag))[0]) for temptag in tags if re.findall(r'\d+', str(temptag))])
            except: last_tag = 0
            tag = f'var{last_tag+1}'
            self.tag = tag
            self._api = self.model.variable().create(self.tag)
            if self.comp is None: self.comsol.childs.append(self)
            else:
                self.comp.childs.append(self)
                self.set_component(self.comp.tag)
            logger.info(f"Variable collection {self.tag} created.")
        else:         
            self.tag = tag
            self._api = self.model.variable(self.tag)
            if self.comp is None:
                if self.tag not in self.comsol.get_childs():
                    self.comsol.childs.append(self)
            else:
                if self.tag not in self.comp.get_childs():
                    self.comp.childs.append(self)
        
            logger.info(f"Variable collection {self.tag} loaded.")

    def set_variable(self,
                    name: str,
                    expression: str,
                    description: str | None = None):
        """Set a variable expression in this collection.

        Category: COMSOL management.
        Tags: comsol, variables, expression.
        Use when: changing a COMSOL variable before running or saving a model.
        Parameters:
            name (str): The name of the variable.
            expression (str): The expression of the variable.
            description (str): the description of the variable. Defaults to None.
        Side effects:
            Calls the COMSOL API ``set`` method.
        """
        if description is not None: self._api.set(name, expression, description)
        else: self._api.set(name, expression)
        

    def get_variables(self):
        """Return variables as a pandas DataFrame.

        Category: COMSOL management.
        Tags: comsol, variables, dataframe.
        Use when: inspecting variable names, expressions, and descriptions.
        Returns:
            pd.DataFrame: Columns ``Name``, ``Expression``, and ``Description``.
        """
        names = self._api.varnames()
        expr = []
        descr = []
        names_str = []
        for name in names:
            names_str.append(str(name))
            expr.append(str(self._api.get(name)))
            descr.append(str(self._api.descr(name)))

        
        df = pd.DataFrame()
        df['Name'] = names_str
        df['Expression'] = expr
        df['Description'] = descr
        return df

    def set_component(self, comp_tag: str):
        """Move this variable collection to a component or global scope.

        Category: COMSOL management.
        Tags: comsol, variables, component-scope.
        Use when: reassigning where a COMSOL variable collection lives.
        Parameters:
            comp_tag (str): The tag of the component or "" to be global.
        Side effects:
            Updates the COMSOL variable model scope and pydelling child
            registries.
        """
        self._api.model(comp_tag)
        if self.comp is not None:
            if self.comp.tag != comp_tag:
                for i in range(len(self.comp.childs)):
                    if self.comp.childs[i].tag == self.tag:
                        del self.comp.childs[i]
                        self.comp = None

        if comp_tag != "":
            inchild = False
            for child in self.comsol.childs:
                if child.tag == comp_tag:
                    self.comp = child
                    inchild = True
            if not inchild: self.comp = self.comsol.component(comp_tag)
            self.comp.childs.append(self)
            
        

    def apply(self):
        """Placeholder for applying variable-collection changes.

        Category: COMSOL management.
        Tags: comsol, variables, apply, extension-point.
        Use when: extending COMSOL variable wrappers with explicit apply
            behavior.
        """
        pass

class ComsolParameters:
    """Wrapper around the global COMSOL parameter collection.

    Category: COMSOL management.
    Tags: comsol, parameters, dataframe.
    Use when: an MCP agent needs to set or inspect global COMSOL parameters.
    """

    def __init__(self,
            comsol: 'ComsolManager.ComsolModel'):
        """Load the COMSOL parameter API wrapper.

        Category: COMSOL management.
        Tags: comsol, parameters, initialization.
        Use when: accessing global model parameters.
        Parameters:
            parent (ComsolModel): The ComsolModel object where the variable lives.
        Side effects:
            Stores COMSOL model references and the ``model.param()`` API object.
        """
        self.comsol = comsol
        self.manager = self.comsol.manager
        self.model = self.comsol.model

        self.tag = None

        self._api = self.model.param()
    
        logger.info(f"Parameters collection loaded.")

    def set_parameter(self,
                    name: str,
                    expression: str,
                    description: str | None = None):
        """Set a global COMSOL parameter expression.

        Category: COMSOL management.
        Tags: comsol, parameters, expression.
        Use when: changing a model parameter before running a study.
        Parameters:
            name (str): The name of the parameter.
            expression (str): The expression of the parameter.
            description (str): the description of the parameter. Defaults to None.
        Side effects:
            Calls the COMSOL API ``set`` method.
        """
        if description is not None: self._api.set(name, expression, description)
        else: self._api.set(name, expression)
        
    def get_parameters(self):
        """Return parameters as a pandas DataFrame.

        Category: COMSOL management.
        Tags: comsol, parameters, dataframe.
        Use when: inspecting parameter names, expressions, and descriptions.
        Returns:
            pd.DataFrame: Columns ``Name``, ``Expression``, and ``Description``.
        """
        names = self._api.varnames()
        expr = []
        descr = []
        names_str = []
        for name in names:
            names_str.append(str(name))
            expr.append(str(self._api.get(name)))
            descr.append(str(self._api.descr(name)))

        
        df = pd.DataFrame()
        df['Name'] = names_str
        df['Expression'] = expr
        df['Description'] = descr
        return df
    
    def apply(self):
        """Placeholder for applying parameter changes.

        Category: COMSOL management.
        Tags: comsol, parameters, apply, extension-point.
        Use when: extending COMSOL parameter wrappers with explicit apply
            behavior.
        """
        pass
