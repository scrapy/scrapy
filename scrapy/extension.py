from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list

class ExtensionManager(MiddlewareManager):
    """Loads and tracks :ref:`extensions <topics-extensions>` configured using
    :setting:`EXTENSIONS`."""

    component_name = 'extension'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(settings.getwithbase('EXTENSIONS'))
