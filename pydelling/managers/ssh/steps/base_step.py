from pydelling.managers import BaseManager
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

def manager_decorator(func):
    """Decorator to add the manager to the step"""
    def wrapper(self, manager: BaseManager = None, **kwargs):
        if manager is None:
            assert self.manager is not None, 'Manager not defined'
            manager = self.manager
        return func(self, manager, **kwargs)
    return wrapper

class BaseStep(ABC):
    """Defines the base step class. The step class is supposed to save a ssh operation and execute it later on"""
    def __init__(self,
                 manager: BaseManager = None,
                 kind='pre',
                 **kwargs,
                 ):
        self.manager = None
        self.kind = kind

    @manager_decorator
    def run(self, manager: BaseManager = None):
        """Runs the step"""
        self._run(manager)
        logger.info(f'Running ssh step {self.__class__.__name__}')

    @abstractmethod
    def _run(self, manager: BaseManager = None):
        """Runs the step, should be implemented by the subclasses"""
        pass



