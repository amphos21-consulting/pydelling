"""
Module documentation.


"""

from .base_step import BaseStep

class CopyStep(BaseStep):
    def __init__(self, src, dst, remote=True):
        """
        __init__ method.
        
        Args:
            src (Any): Description.
            dst (Any): Description.
            remote (Any): Description.
        """
        super().__init__()
        self.src = src
        self.dst = dst
        self.remote = remote

    def _run(self, manager):
        """
        Runs the step
        
        Args:
            manager (Any): Description.
        """
        if self.remote:
            manager.ssh.cp_remote(self.src, self.dst)
        else:
            manager.ssh.cp(self.src, self.dst)