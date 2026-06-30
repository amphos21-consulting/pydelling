"""This is the base class used to build other webapps."""

import inspect
import subprocess
from abc import ABC
import streamlit as st
from .base_streamlit_utility_class import BaseStreamlitUtilityClass


class WebAppRunner(ABC, BaseStreamlitUtilityClass):
    """Base runner for pydelling Streamlit webapps.

    Category: Web application.
    Tags: streamlit, webapp, runner, lifecycle.
    Usage: to understand the legacy webapp runner import
        path and how pydelling webapps launch or render inside Streamlit.
    """

    def __init__(self):
        self.source_script_name = None
        if "threading" not in inspect.stack()[-1][1]:
            self.source_script_name = inspect.stack()[-1][1]

    def construct(self):
        """This is the main method that builds the webapp."""
        pass

    def run(self):
        """This is the main method that runs the webapp."""
        current_executer = inspect.stack()
        if "threading" not in current_executer[-1][1]:
            subprocess.run(["streamlit", "run", self.source_script_name])
        else:
            self.initialize()
            self.construct()

    def initialize(self):
        """This method initializes the webapp."""
        pass
