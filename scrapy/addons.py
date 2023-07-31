import logging
from typing import TYPE_CHECKING, Any, List

from scrapy.exceptions import NotConfigured
from scrapy.settings import Settings
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

    def _add(self, addon: Any, settings: Settings) -> None:
        """Store an add-on."""
        if isinstance(addon, (type, str)):
            addon = load_object(addon)
        if isinstance(addon, type):
            addon = create_instance(addon, settings=None, crawler=self.crawler)
        try:
            addon.update_settings(settings)
            self.addons.append(addon)
        except NotConfigured:
            pass

    def load_settings(self, settings: Settings) -> None:
        """Load add-ons and configurations from a settings object.

        This will load the add-on for every add-on path in the
        ``ADDONS`` setting and execute their ``update_settings`` methods.

        :param settings: The :class:`~scrapy.settings.Settings` object from \
            which to read the add-on configuration
        :type settings: :class:`~scrapy.settings.Settings`
        """
        addons = build_component_list(settings["ADDONS"])
        for addon in build_component_list(settings["ADDONS"]):
            self._add(addon, settings)
        logger.info(
            "Enabled addons:\n%(addons)s",
            {
                "addons": addons,
            },
            extra={"crawler": self.crawler},
        )
