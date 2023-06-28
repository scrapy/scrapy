from typing import Any, List

from scrapy.utils.conf import build_component_list
from scrapy.utils.misc import load_object


class AddonManager:
    """This class facilitates loading and storing :ref:`topics-addons`."""

    def __init__(self) -> None:
        self.addons: List[Any] = []

    def add(self, addon: Any) -> None:
        """Store an add-on.

        :param addon: The add-on object (or path) to be stored
        :type addon: Python object, class or ``str``

        :param config: The add-on configuration dictionary
        :type config: ``dict``
        """
        if isinstance(addon, (type, str)):
            addon = load_object(addon)
        if isinstance(addon, type):
            addon = addon()
        self.addons.append(addon)

    def load_settings(self, settings) -> None:
        """Load add-ons and configurations from settings object.

        This will load the addon for every add-on path in the
        ``ADDONS`` setting.

        :param settings: The :class:`~scrapy.settings.Settings` object from \
            which to read the add-on configuration
        :type settings: :class:`~scrapy.settings.Settings`
        """
        paths = build_component_list(settings["ADDONS"])
        addons = [load_object(path) for path in paths]
        for a in addons:
            self.add(a)

    def update_settings(self, settings) -> None:
        """Call ``update_settings()`` of all held add-ons.

        :param settings: The :class:`~scrapy.settings.Settings` object to be \
            updated
        :type settings: :class:`~scrapy.settings.Settings`
        """
        for addon in self.addons:
            addon.update_settings(settings)
