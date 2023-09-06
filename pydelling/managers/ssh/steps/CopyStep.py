from .BaseStep import BaseStep

class CopyStep(BaseStep):
    def __init__(self, src, dst, remote=True):
        super().__init__()
        self.src = src
        self.dst = dst
        self.remote = remote

    def _run(self, manager):
        """Runs the step"""
        if self.remote:
            manager.ssh.cp_remote(self.src, self.dst)
        else:
            manager.ssh.cp(self.src, self.dst)