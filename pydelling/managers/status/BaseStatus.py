"""
The base class for all status classes. This class should read a given status file and extract some key information.


"""

import os

class BaseStatus:
    """Base status-file reader for simulation progress helpers.

    Category: simulation status.
    Tags: status-file, progress, simulation, extension-point.
    Usage: to understand the common contract for status
        parsers such as PFLOTRAN status readers.
    """

    def __init__(self, status_file, ssh_manager=None):
        """
        Initialize the BaseStatus class with the given status file.
        
        Args:
            status_file (Any): Description.
            ssh_manager (Any): Description.
        """
        if not os.path.exists(status_file):
            raise FileNotFoundError(f"Status file {status_file} not found.")
        self.status_file = status_file
        self.status_data = None
        self.ssh_manager = ssh_manager
        self.read_status_file()

    def read_status_file(self):
        """Read the status file and store its content."""
        # if self.ssh_manager is not None:
        #     self.status_data = self.ssh_manager.get(self.status_file
        with open(self.status_file, "r") as file:
            self.status_data = file.read()

    def extract_key_information(self):
        """Extract key information from the status data."""
        raise NotImplementedError("This method should be implemented in a derived class.")

    @property
    def progress(self):
        """Return the progress of the simulation."""
        raise NotImplementedError("This method should be implemented in a derived class.")
