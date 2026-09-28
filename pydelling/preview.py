"""Compatibility exports for the asset preview API.

New integrations should import from :mod:`pydelling.assets`. This module is
retained for at least the Pydelling 1.2 minor release.
"""

from pydelling.assets.handlers import *  # noqa: F403
from pydelling.assets.handlers import PREVIEW_CONTRACT_VERSION
