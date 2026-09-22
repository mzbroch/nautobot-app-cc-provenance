"""App declaration for nautobot_cc_provenance."""

# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

from nautobot.apps import NautobotAppConfig

__version__ = metadata.version(__name__)


class CcProvenanceConfig(NautobotAppConfig):
    """App configuration for the nautobot_cc_provenance app."""

    name = "nautobot_cc_provenance"
    verbose_name = "Config Context Provenance"
    version = __version__
    author = "Network to Code, LLC"
    description = "Explains which config context supplied each key of a merged config context."
    base_url = "cc-provenance"
    required_settings = []
    default_settings = {}
    docs_view_name = "plugins:nautobot_cc_provenance:docs"
    searchable_models = []


config = CcProvenanceConfig  # pylint:disable=invalid-name
