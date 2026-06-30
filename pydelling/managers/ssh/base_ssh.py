"""
Module documentation.


"""

from abc import ABC, abstractmethod
import pandas as pd
import paramiko
import logging
logger = logging.getLogger(__name__)
from pathlib import Path

class BaseSsh(ABC):
    """Abstract SSH/SFTP helper used by remote simulation managers.

    Category: Remote execution.
    Tags: ssh, sftp, hpc, files, commands, remote-manager.
    Use when: to understand how pydelling managers run shell
        commands and move files on remote HPC systems.
    """

    client: paramiko.SSHClient
    sftp: paramiko.SFTPClient
    def __init__(self,
                 user,
                 pkey_path,
                 project_name=None,
                 password=None,
                 ):
        """Store credentials and open the remote connection.

        Category: Remote execution.
        Tags: ssh, credentials, connection, initialization.
        Use when: creating a platform-specific SSH helper such as JURECA or
            LUMI.
        Args:
            user: Remote username.
            pkey_path: Path to the private key used for authentication.
            project_name: Optional HPC project or allocation name.
            password: Optional password used by platform-specific connectors.
        Side effects:
            Calls the subclass ``connect`` implementation.
        """
        self.pkey_path = pkey_path
        self.user = user
        self.password = password
        self.connect()

    @abstractmethod
    def connect(self):
        """Open ``self.client`` and ``self.sftp`` for the target platform.

        Category: Remote execution.
        Tags: ssh, sftp, connection, extension-point.
        Use when: implementing a concrete remote platform connector.
        Side effects:
            Implementations should create an authenticated Paramiko SSH client
            and SFTP client.
        """
        pass

    def run_command(self, command):
        """Run a shell command on the remote server.

        Category: Remote execution.
        Tags: ssh, command, remote-shell.
        Use when: a manager needs to submit jobs, copy files remotely, or query
            the HPC filesystem.
        Args:
            command: Shell command to execute through Paramiko.
        Returns:
            Decoded stdout with surrounding whitespace removed.
        """
        stdin, stdout, stderr = self.client.exec_command(command)
        return stdout.read().decode('utf-8').strip()

    def cp_remote(self, src, dst):
        """Copy a remote file to another remote path.

        Category: Remote execution.
        Tags: ssh, remote-copy, file.
        Use when: a workflow needs a server-side file copy without downloading
            the file locally.
        Args:
            src: Source path on the remote server.
            dst: Destination path on the remote server.
        Side effects:
            Executes ``cp`` remotely.
        """
        self.run_command(f'cp {src} {dst}')
        logger.info(f'Copied (remote -> remote) {src} to {dst}')

    def cpdir_remote(self, src, dst):
        """Copy a remote directory tree to another remote path.

        Category: Remote execution.
        Tags: ssh, remote-copy, directory.
        Use when: a workflow needs a server-side recursive copy of study files or
            results.
        Args:
            src: Source directory on the remote server.
            dst: Destination directory on the remote server.
        Side effects:
            Executes ``cp -r`` remotely.
        """
        self.run_command(f'cp -r {src} {dst}')
        logger.info(f'Copied (remote -> remote) {src} to {dst}')


    @property
    def pwd(self):
        """Return the SFTP current working directory.

        Category: Remote execution.
        Tags: sftp, working-directory, remote.
        Use when: a workflow needs to know the current remote SFTP context.
        Returns:
            Remote working directory path reported by Paramiko SFTP.
        """
        return self.sftp.getcwd()

    def cd(self, path):
        """Change the current SFTP working directory.

        Category: Remote execution.
        Tags: sftp, working-directory, cd.
        Use when: subsequent relative SFTP operations should target a remote
            study folder.
        Args:
            path: Remote directory to switch to.
        Side effects:
            Updates Paramiko SFTP working directory.
        """
        path = str(path)
        self.sftp.chdir(path)
        logger.info(f'Changed directory to {path}')

    def mkdir(self, path):
        """Create a remote directory if it is not already listed.

        Category: Remote execution.
        Tags: sftp, mkdir, remote-directory.
        Use when: preparing remote study or results folders.
        Args:
            path: Remote directory path to create.
        Side effects:
            Calls ``sftp.mkdir`` when the directory name is absent.
        """
        path = Path(path)
        if path.name in self.ls:
            logger.info(f'Directory {path} already exists')
            return
        else:
            self.sftp.mkdir(str(path))
            logger.info(f'Created directory {path}')

    def rm(self, path: str):
        """Remove a remote file through SFTP.

        Category: Remote execution.
        Tags: sftp, remove, remote-file.
        Use when: cleaning remote files generated by a study workflow.
        Args:
            path: Remote file path to remove.
        Side effects:
            Deletes the file from the remote server.
        """
        path = str(path)
        self.sftp.remove(path)
        logger.info(f'Removed (remote) file {path}')

    def rmdir(self,
              path: str,
              ):
        """Recursively remove a remote directory through SFTP.

        Category: Remote execution.
        Tags: sftp, remove, remote-directory, recursive.
        Use when: cleaning complete remote study folders.
        Args:
            path: Remote directory path to remove.
        Side effects:
            Removes nested files/directories and then the root directory.
        """
        path = Path(path)
        for file in self.sftp.listdir(str(path)):
            try:
                self.rm(str(path / file))
            except IOError:
                self.rmdir(str(path / file))
        self.sftp.rmdir(str(path))
        logger.info(f'Removed (remote) directory {path}')

    def cp(self, src, dst):
        """Upload a local file to the remote server.

        Category: Remote execution.
        Tags: sftp, upload, file.
        Use when: sending solver inputs, scripts, or assets to an HPC workspace.
        Args:
            src: Local source file.
            dst: Remote destination file.
        Side effects:
            Uploads the file through SFTP.
        """
        self.sftp.put(src, dst)
        logger.info(f'Copied (local -> remote) {src} to {dst}')

    def cpdir(self, src, dst):
        """Recursively upload a local directory to the remote server.

        Category: Remote execution.
        Tags: sftp, upload, directory, recursive.
        Use when: transferring a complete study folder to a remote HPC system.
        Args:
            src: Local source directory.
            dst: Remote destination directory.
        Side effects:
            Creates the destination directory and uploads contained files.
        """
        src = Path(src)
        dst = Path(dst)

        self.mkdir(str(dst))
        for file in src.iterdir():
            if file.is_dir():
                self.cpdir(file, str(dst / file.name))
            else:
                self.cp(file, str(dst / file.name))

    def get(self, src, dst):
        """Download a remote file to the local machine.

        Category: Remote execution.
        Tags: sftp, download, file.
        Use when: retrieving solver outputs or logs from a remote run.
        Args:
            src: Remote source file.
            dst: Local destination file.
        Side effects:
            Downloads the file through SFTP.
        """
        self.sftp.get(src, dst)
        logger.info(f'Copied (remote -> local) {src} to {dst}')

    def getdir(self, src, dst):
        """Download files from a remote directory into a local directory.

        Category: Remote execution.
        Tags: sftp, download, directory.
        Use when: retrieving result files from the current remote study folder.
        Args:
            src: Remote source directory.
            dst: Local destination directory.
        Side effects:
            Creates the local directory, changes remote SFTP directory, and
            downloads listed files.
        """
        src = Path(src)
        dst = Path(dst)

        dst.mkdir(parents=True, exist_ok=True)
        self.cd(src)
        for file in self.ls:
            self.get(file, dst / Path(file).name)


    @property
    def ls(self):
        """List the current remote SFTP directory.

        Category: Remote execution.
        Tags: sftp, listdir, remote-directory.
        Use when: checking whether remote files or folders exist before
            transfer operations.
        Returns:
            List of names in the current remote directory.
        """
        return self.sftp.listdir()

    def ls_dir(self, dir):
        """List a specific remote directory.

        Category: Remote execution.
        Tags: sftp, listdir, remote-directory.
        Use when: an MCP workflow needs directory contents without changing the
            current SFTP working directory.
        Args:
            dir: Remote directory path to list.
        Returns:
            List of names in ``dir``.
        """
        return self.sftp.listdir(dir)

    @abstractmethod
    def cd_studies_folder(self, project_name):
        """Change into the platform-specific remote studies folder.

        Category: Remote execution.
        Tags: ssh, hpc, studies, extension-point.
        Use when: a concrete HPC connector must locate the workspace where
            pydelling studies should be uploaded and run.
        Args:
            project_name: Remote allocation or project name used to locate the
                studies folder.
        Returns:
            Platform implementations should change directory and return their
            own result, if any.
        """
        return NotImplementedError('Method not implemented')
