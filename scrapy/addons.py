from typing import Any, Dict, Iterator, Mapping, Optional, OrderedDict

from scrapy.utils.conf import build_component_list
from scrapy.utils.misc import load_object


class Addon(object):
    name: str

    default_config = None
    """``dict`` with default configuration."""

    config_mapping = None
    """``dict`` with mappings from config names to setting names. The given
    setting names will be taken as given, not uppercased.
    """

    def export_config(self, config, settings):
        """Export the add-on configuration, all keys in caps, into the settings
        object.

        For example, the add-on configuration ``{'key': 'value'}`` will export
        the setting ``KEY`` with a value of ``value``. All settings
        will be exported with ``addon`` priority (see
        :ref:`topics-api-settings`).

        :param config: Add-on configuration to be exposed
        :type config: ``dict``

        :param settings: Settings object into which to export the configuration
        :type settings: :class:`~scrapy.settings.Settings`
        """
        conf = self.default_config or {}
        conf.update(config)
        # Since default exported config is case-insensitive (everything will be
        # uppercased), make mapped config case-insensitive as well
        conf_mapping = {k.lower(): v for k, v in (self.config_mapping or {}).items()}
        for key, val in conf.items():
            if key.lower() in conf_mapping:
                key = conf_mapping[key.lower()]
            else:
                key = key.upper()
            settings.set(key, val, "addon")

    def update_settings(self, config, settings):
        """Modifiy `settings` to enable and configure required components.

        :param config: Add-on configuration
        :type config: ``dict``

        :param settings: Crawler settings object
        :type settings: :class:`~scrapy.settings.Settings`
        """
        self.export_config(config, settings)

    def check_configuration(self, config, crawler):
        """Perform post-initialization checks on fully configured `crawler`.

        :param config: Add-on configuration
        :type config: ``dict``

        :param crawler: the fully-initialized crawler
        :type crawler: :class:`~scrapy.crawler.Crawler`
        """
        pass


class AddonManager(Mapping[str, Addon]):
    """This class facilitates loading and storing :ref:`topics-addons`.

    You can treat it like a read-only dictionary in which keys correspond to
    add-on names and values correspond to the add-on objects. Add-on
    configurations are saved in the :attr:`config` dictionary attribute::

        addons = AddonManager()
        # ... load some add-ons here
        print(addons.enabled)  # prints names of all enabled add-ons
        print(addons['TestAddon'].version)  # prints version of add-on with name
                                           # 'TestAddon'
        print(addons.configs['TestAddon'])  # prints configuration of 'TestAddon'

    """

    def __init__(self) -> None:
        self._addons: OrderedDict[str, Addon] = OrderedDict[str, Addon]()
        self.configs: Dict[str, Dict[str, Any]] = {}

    def __getitem__(self, name: str) -> Addon:
        return self._addons[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._addons)

    def __len__(self) -> int:
        return len(self._addons)

    def add(self, addon: Any, config: Optional[Dict[str, Any]] = None):
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
        name = addon.name
        if name in self:
            raise ValueError(f"Addon '{name}' already loaded")
        self._addons[name] = addon
        self.configs[name] = config or {}

    def load_settings(self, settings):
        """Load add-ons and configurations from settings object.

        This will load the addon for every add-on path in the
        ``ADDONS`` setting. For each of these add-ons, the configuration will be
        read from the dictionary setting whose name matches the uppercase add-on
        name.

        :param settings: The :class:`~scrapy.settings.Settings` object from \
            which to read the add-on configuration
        :type settings: :class:`~scrapy.settings.Settings`
        """
        paths = build_component_list(settings["ADDONS"])
        addons = [load_object(path) for path in paths]
        configs = [settings.getdict(addon.name.upper()) for addon in addons]
        for a, c in zip(addons, configs):
            self.add(a, c)

    def update_settings(self, settings) -> None:
        """Call ``update_settings()`` of all held add-ons.

        :param settings: The :class:`~scrapy.settings.Settings` object to be \
            updated
        :type settings: :class:`~scrapy.settings.Settings`
        """
        for name in self:
            self[name].update_settings(self.configs[name], settings)

    def check_configuration(self, crawler) -> None:
        """Call ``check_configuration()`` of all held add-ons.

        :param crawler: the fully-initialized crawler
        :type crawler: :class:`~scrapy.crawler.Crawler`
        """
        for name in self:
            self[name].check_configuration(self.configs[name], crawler)
