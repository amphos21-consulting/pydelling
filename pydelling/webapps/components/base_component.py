"""
Module documentation.


"""

from abc import ABC, abstractmethod

from pydelling.webapps import WebAppRunner
from translate import Translator
import streamlit as st
import extra_streamlit_components as stx
from ..base_streamlit_utility_class import BaseStreamlitUtilityClass

class BaseComponent(ABC, BaseStreamlitUtilityClass):
    """Abstract Streamlit component base with session-state initialization.

    Category: Web application component.
    Tags: streamlit, component, session-state, translation.
    Use when: to understand the common lifecycle for
        pydelling Streamlit components.
    """

    _value = None
    def __init__(self,
                 webapp: WebAppRunner=None,
                 lang=None,
                 translate=False,
                 key=None,
                 *args,
                 **kwargs
                 ):
        """Initialize component state and immediately render it.

        Category: Web application component.
        Tags: streamlit, component, initialization, translation.
        Use when: constructing reusable pydelling UI components.
        Args:
            webapp: Optional owning webapp runner.
            lang: Optional target language for ``translate.Translator``.
            translate: Whether translation is enabled.
            key: Optional suffix used to build the component session-state name.
            *args: Positional arguments forwarded to ``run``.
            **kwargs: Extra attributes copied onto the component and forwarded to
                ``run``.
        Side effects:
            Initializes ``<name>-init`` in Streamlit session state and calls
            ``run``.
        """
        self.type = self.__class__.__name__
        self.finished = False
        self.translate = translate

        for kwarg in kwargs:
            setattr(self, kwarg, kwargs[kwarg])

        if webapp:
            self.webapp = webapp
        if lang is not None:
            self.translator = Translator(to_lang=lang)
            self.translate = True
        self.name = f'{self.type}{key if key is not None else ""}'
        self.initialize_in_session_state(key=f'{self.name}-init', value=False)
        self.run(*args, **kwargs)

    @abstractmethod
    def run(self, *args, **kwargs):
        """Render or execute the component.

        Category: Web application component.
        Tags: streamlit, component, lifecycle, extension-point.
        Use when: implementing a concrete component subclass.
        Args:
            *args: Component-specific positional arguments.
            **kwargs: Component-specific keyword arguments.
        """

    @property
    def value(self):
        """Return the component's current value.

        Category: Web application component.
        Tags: streamlit, component, value.
        Use when: callers need the object produced by a component interaction.
        Returns:
            Any: Value stored in ``self._value``.
        """
        return self._value
