import logging
from typing import TYPE_CHECKING, Any, List

from scrapy.utils.conf import build_component_list
from scrapy.utils.misc import create_instance, load_object

if TYPE_CHECKING:
    from scrapy.crawler import Crawler

logger = logging.getLogger(__name__)


class AddonManager:
    """This class facilitates loading and storing :ref:`topics-addons`."""

    def __init__(self, crawler: "Crawler") -> None:
        self.crawler: "Crawler" = crawler
        self.addons: List[Any] = []

    def _add(self, addon: Any) -> None:
        """Store an add-on."""
        if isinstance(addon, (type, str)):
            addon = load_object(addon)
        if isinstance(addon, type):
            addon = create_instance(addon, settings=None, crawler=self.crawler)
        self.addons.append(addon)

    def load_settings(self, settings) -> None:
        """Load add-ons and configurations from a settings object.

        This will load the add-on for every add-on path in the
        ``ADDONS`` setting.

        :param settings: The :class:`~scrapy.settings.Settings` object from \
            which to read the add-on configuration
        :type settings: :class:`~scrapy.settings.Settings`
        """
        addons = build_component_list(settings["ADDONS"])
        for addon in build_component_list(settings["ADDONS"]):
            self._add(addon)
        logger.info(
            "Enabled addons:\n%(addons)s",
            {
                "addons": addons,
            },
            extra={"crawler": self.crawler},
        )

    def update_settings(self, settings) -> None:
        """Call ``update_settings()`` of all held add-ons.

        :param settings: The :class:`~scrapy.settings.Settings` object to be \
            updated
        :type settings: :class:`~scrapy.settings.Settings`
        """
        for addon in self.addons:
            addon.update_settings(settings)