"""
This class contains basic function definitions of the different GiD objects
"""

class _AbstractGidObject(object):
    """Minimal interface for objects that emit GiD batch commands.

    Category: GID preprocessing.
    Tags: gid, geometry, batch-command, extension-point.
    Usage: to understand the shared contract for point, line, surface,
        and other GiD objects that can generate command text.
    """

    def create_gid_bash(self) -> str:
        """
        This method should create a string that contains the bash code to generate the object in GiD
        Returns:
            Bash string
        """
        return ''
