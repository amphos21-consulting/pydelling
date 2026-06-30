"""
Defines the base step class. The step class is supposed to save a ssh operation and execute it later on


"""

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
    """Base class for deferred SSH manager steps.

    Category: Remote execution.
    Tags: ssh, step, callback, deferred-operation.
    Use when: an MCP agent needs to understand how pydelling stores remote
        operations for execution during manager workflows.
    """

    def __init__(self,
                 manager: BaseManager = None,
                 kind='pre',
                 **kwargs,
                 ):
        """Initialize a deferred SSH step.

        Category: Remote execution.
        Tags: ssh, step, initialization.
        Use when: creating an operation that will later run with a
            ``BaseManager``.
        Args:
            manager: Optional manager used when ``run`` is called without one.
            kind: Step phase, commonly ``"pre"`` or ``"post"``.
            **kwargs: Extra subclass-specific options.
        """
        self.manager = None
        self.kind = kind

    @manager_decorator
    def run(self, manager: BaseManager = None):
        """Run the concrete SSH step with a manager.

        Category: Remote execution.
        Tags: ssh, step, run.
        Use when: executing a stored remote operation.
        Args:
            manager: Manager that provides SSH access and workflow context.
        Side effects:
            Calls the subclass ``_run`` implementation and logs execution.
        """
        self._run(manager)
        logger.info(f'Running ssh step {self.__class__.__name__}')

    @abstractmethod
    def _run(self, manager: BaseManager = None):
        """Execute the concrete step implementation.

        Category: Remote execution.
        Tags: ssh, step, extension-point.
        Use when: implementing a concrete SSH operation subclass.
        Args:
            manager: Manager that provides SSH access and workflow context.
        """
        pass
