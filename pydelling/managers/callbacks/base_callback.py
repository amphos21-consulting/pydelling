"""Base callback interfaces used by study managers.


"""

from pydelling.managers import BaseManager, BaseStudy
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class BaseCallback(ABC):
    def __init__(self, manager: BaseManager, study: BaseStudy, kind: str = None, **kwargs):
        """
        Initialize callback context and user-provided options.
        
        Args:
            manager (BaseManager): Description.
            study (BaseStudy): Description.
            kind (str): Description.
            **kwargs (Any): Description.
        """
        self.manager = manager
        self.study = study
        assert kind in ['pre', 'post'], f"Kind must be 'pre' or 'post', not {kind}"
        self.kind = kind
        self.kwargs = kwargs
        self.is_run = False
        self.process_kwargs()

    @abstractmethod
    def run(self, on_remote=False):
        """This method executes the callback.
        Args:
            on_remote (optional): Indicates if running on remote. Default is None.
        """
        self.is_run = True
        logger.info(f"Running callback {self.__class__.__name__} for study {self.study.name}")
        pass

    def process_kwargs(self):
        """Expose callback kwargs as instance attributes.

        
        """
        for kwarg_name, kwarg in self.kwargs.items():
            setattr(self, kwarg_name, kwarg)
