"""
Module documentation.


"""

from .base_step import BaseStep

class CopyStep(BaseStep):
    """Deferred SSH copy operation.

    Category: Remote execution.
    Tags: ssh, sftp, copy, step.
    Use when: an MCP agent needs to understand how pydelling schedules local or
        remote file copies during SSH-backed manager workflows.
    """

    def __init__(self, src, dst, remote=True):
        """Create a deferred copy step.

        Category: Remote execution.
        Tags: ssh, copy, initialization.
        Use when: storing a copy operation for later execution by a manager.
        Args:
            src: Source path.
            dst: Destination path.
            remote: If ``True``, copy remote-to-remote; otherwise upload
                local-to-remote.
        """
        super().__init__()
        self.src = src
        self.dst = dst
        self.remote = remote

    def _run(self, manager):
        """Execute the copy through the manager's SSH helper.

        Category: Remote execution.
        Tags: ssh, copy, sftp, run.
        Use when: applying a deferred copy operation during a remote workflow.
        Args:
            manager: Manager with an initialized ``ssh`` helper.
        Side effects:
            Calls ``cp_remote`` or ``cp`` on ``manager.ssh``.
        """
        if self.remote:
            manager.ssh.cp_remote(self.src, self.dst)
        else:
            manager.ssh.cp(self.src, self.dst)
