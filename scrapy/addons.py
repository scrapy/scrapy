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

    def load_settings(self, settings: Settings) -> None:
        """Load add-ons and configurations from a settings object.

        This will load the add-on for every add-on path in the
        ``ADDONS`` setting and execute their ``update_settings`` methods.

        :param settings: The :class:`~scrapy.settings.Settings` object from \
            which to read the add-on configuration
        :type settings: :class:`~scrapy.settings.Settings`
        """
        enabled: List[Any] = []
        for clspath in build_component_list(settings["ADDONS"]):
            try:
                addoncls = load_object(clspath)
                addon = create_instance(
                    addoncls, settings=settings, crawler=self.crawler
                )
                addon.update_settings(settings)
                self.addons.append(addon)
            except NotConfigured as e:
                if e.args:
                    logger.warning(
                        "Disabled %(clspath)s: %(eargs)s",
                        {"clspath": clspath, "eargs": e.args[0]},
                        extra={"crawler": self.crawler},
                    )
        logger.info(
            "Enabled addons:\n%(addons)s",
            {
                "addons": enabled,
            },
            extra={"crawler": self.crawler},
        )
