from collections import defaultdict, Mapping, OrderedDict
from inspect import isclass
import six
import warnings

from pkg_resources import WorkingSet, Distribution, Requirement
import zope.interface
from zope.interface.verify import verifyObject

from scrapy.interfaces import IAddon
from scrapy.utils.conf import build_component_list
from scrapy.utils.misc import load_module_or_object


@zope.interface.implementer(IAddon)
class Addon(object):

    basic_settings = None
    """``dict`` of settings that will be exported via :meth:`export_basics`."""

    default_config = None
    """``dict`` with default configuration."""

    config_mapping = None
    """``dict`` with mappings from config names to setting names. The given
    setting names will be taken as given, i.e. they will be neither prefixed
    nor uppercased.
    """

    component_type = None
    """Component setting into which to export via :meth:`export_component`. Can
    be any of the dictionary-like component setting names (e.g.
    ``DOWNLOADER_MIDDLEWARES``) or any of their abbreviations in
    :attr:`~scrapy.addons.COMPONENT_TYPE_ABBR`. If ``None``,
    :meth:`export_component` will do nothing.
    """

    component_key = None
    """Key to be used in the component dictionary setting when exporting via
    :meth:`export_component`. This is only useful for the settings that have
    no order, e.g. ``DOWNLOAD_HANDLERS`` or ``FEED_EXPORTERS``.
    """

    component_order = 0
    """Component order to use when not given in the add-on configuration. Has
    no effect for component types that use :attr:`component_key`.
    """

    component = None
    """Component to be inserted via :meth:`export_component`. This can be
    anything that can be used in the dictionary-like component settings, i.e.
    a class path, a class, or an instance. If ``None``, it is assumed that the
    add-on itself is also provides the component interface, and ``self`` will be
    used.
    """

    settings_prefix = None
    """Prefix with which the add-on configuration will be exported into the
    global settings namespace via :meth:`export_config`. If ``None``,
    :attr:`name` will be used. If ``False``, no configuration will be exported.
    """

    def export_component(self, config, settings):
        """Export the component in :attr:`component` into the dictionary-like
        component setting derived from :attr:`component_type`.

        Where applicable, the order parameter of the component (i.e. the
        dictionary value) will be retrieved from the ``order`` add-on
        configuration value.

        :param config: Add-on configuration from which to read component order
        :type config: ``dict``

        :param settings: Settings object into which to export component
        :type settings: :class:`~scrapy.settings.Settings`
        """
        if self.component_type:
            comp = self.component or self
            if self.component_key:
                # e.g. for DOWNLOAD_HANDLERS: {'http': 'myclass'}
                k = self.component_key
                v = comp
            else:
                # e.g. for DOWNLOADER_MIDDLEWARES: {'myclass': 100}
                k = comp
                v = config.get('order', self.component_order)
            settings[self.component_type].update({k: v}, 'addon')

    def export_basics(self, settings):
        """Export the :attr:`basic_settings` attribute into the settings object.

        All settings will be exported with ``addon`` priority (see
        :ref:`topics-api-settings`).

        :param settings: Settings object into which to expose the basic settings
        :type settings: :class:`~scrapy.settings.Settings`
        """
        for setting, value in six.iteritems(self.basic_settings or {}):
            settings.set(setting, value, 'addon')

    def export_config(self, config, settings):
        """Export the add-on configuration, all keys in caps and with
        :attr:`settings_prefix` or :attr:`name` prepended, into the settings
        object.

        For example, the add-on configuration ``{'key': 'value'}`` will export
        the setting ``ADDONNAME_KEY`` with a value of ``value``. All settings
        will be exported with ``addon`` priority (see
        :ref:`topics-api-settings`).

        :param config: Add-on configuration to be exposed
        :type config: ``dict``

        :param settings: Settings object into which to export the configuration
        :type settings: :class:`~scrapy.settings.Settings`
        """
        if self.settings_prefix is False:
            return
        conf = self.default_config or {}
        conf.update(config)
        prefix = self.settings_prefix or self.name
        # Since default exported config is case-insensitive (everything will be
        # uppercased), make mapped config case-insensitive as well
        conf_mapping = {k.lower(): v
                        for k, v in six.iteritems(self.config_mapping or {})}
        for key, val in six.iteritems(conf):
            if key.lower() in conf_mapping:
                key = conf_mapping[key.lower()]
            else:
                key = (prefix + '_' + key).upper()
            settings.set(key, val, 'addon')

    def update_settings(self, config, settings):
        """Export both the basic settings and the add-on configuration. I.e.,
        call :meth:`export_basics` and :meth:`export_config`.

        For more advanced add-ons, you may want to override this callback.

        :param config: Add-on configuration
        :type config: ``dict``

        :param settings: Crawler settings object
        :type settings: :class:`~scrapy.settings.Settings`
        """
        self.export_component(config, settings)
        self.export_basics(settings)
        self.export_config(config, settings)


class AddonManager(Mapping):
    """This class facilitates loading and storing :ref:`topics-addons`.

    You can treat it like a read-only dictionary in which keys correspond to
    add-on names and values correspond to the add-on objects. Add-on
    configurations are saved in the :attr:`config` dictionary attribute::

        addons = AddonManager()
        # ... load some add-ons here
        print addons.enabled  # prints names of all enabled add-ons
        print addons['TestAddon'].version  # prints version of add-on with name
                                           # 'TestAddon'
        print addons.configs['TestAddon']  # prints configuration of 'TestAddon'

    """

    def __init__(self):
        self._addons = OrderedDict()
        self.configs = {}
        self._disable_on_add = []

    def __getitem__(self, name):
        return self._addons[name]

    def __delitem__(self, name):
        del self._addons[name]
        del self.configs[name]

    def __iter__(self):
        return iter(self._addons)

    def __len__(self):
        return len(self._addons)

    def add(self, addon, config=None):
        """Store an add-on.

        If ``addon`` is a string, it will be treated as add-on path and passed
        to :meth:`get_addon`. Otherwise, ``addon`` must be a Python object
        implementing or providing Scrapy's add-on interface. The interface
        will be enforced through ``zope.interface``'s ``verifyObject()``.

        If ``addon`` is a class, it will be instantiated. You can avoid this
        (for example if you have implemented the add-on callbacks as class
        methods) by declaring --  via ``zope.interface`` -- that your class
        directly *provides* ``scrapy.interfaces.IAddon``.

        :param addon: The add-on object (or path) to be stored
        :type addon: Any Python object providing the add-on interface or ``str``

        :param config: The add-on configuration dictionary
        :type config: ``dict``
        """
        addon = self.get_addon(addon)
        if isclass(addon) and not IAddon.providedBy(addon):
            addon = addon()
        if not IAddon.providedBy(addon):
            zope.interface.alsoProvides(addon, IAddon)
        # zope.interface's exceptions are already quite helpful. Still, should
        # we catch them and log an error message?
        verifyObject(IAddon, addon)
        name = addon.name
        if name in self:
            raise ValueError("Addon '{}' already loaded".format(name))
        self._addons[name] = addon
        self.configs[name] = config or {}
        if name in self._disable_on_add:
            self.configs[name]['_enabled'] = False
            self._disable_on_add.remove(name)

    def remove(self, addon):
        """Remove an add-on.

        If ``addon`` is the name of a stored add-on, that add-on will be
        removed. Otherwise, you can use the argument in the same fashion as
        in :meth:`add`.

        :param addon: The add-on name, object, or path to be removed
        :type addon: Any Python object providing the add-on interface or ``str``
        """
        if addon in self:
            del self[addon]
        elif hasattr(addon, 'name') and addon.name in self:
            del self[addon.name]
        else:
            try:
                del self[self.get_addon(addon).name]
            except NameError:
                raise KeyError

    @staticmethod
    def get_addon(path):
        """Get an add-on object by its Python or file path.

        ``path`` is assumed to be either a Python or a file path of a Scrapy
        add-on. If the object or module pointed to by ``path`` has an attribute
        named ``_addon`` that attribute will be assumed to be the add-on.
        :meth:`get_addon` will keep following ``_addon`` attributes until it
        finds an object that does not have an attribute named ``_addon``.

        :param path: Python or file path to an add-on
        :type path: ``str``
        """
        if isinstance(path, six.string_types):
            try:
                obj = load_module_or_object(path)
            except NameError:
                raise NameError("Could not find add-on '%s'" % path)
        else:
            obj = path
        if hasattr(obj, '_addon'):
            obj = AddonManager.get_addon(obj._addon)
        return obj

    def load_dict(self, addonsdict):
        """Load add-ons and configurations from given dictionary.

        Each add-on should be an entry in the dictionary, where the key
        corresponds to the add-on path. The value should be a dictionary
        representing the add-on configuration.

        Example add-on dictionary::

            addonsdict = {
                'path.to.addon1': {
                    'setting1': 'value',
                    'setting2': 42,
                    },
                'path/to/addon2.py': {
                    'addon2setting': True,
                    },
                }

        :param addonsdict: dictionary where keys correspond to add-on paths \
            and values correspond to their configuration
        :type addonsdict: ``dict``
        """
        for addonpath, addoncfg in six.iteritems(addonsdict):
            self.add(addonpath, addoncfg)

    def load_settings(self, settings):
        """Load add-ons and configurations from settings object.

        This will invoke :meth:`get_addon` for every add-on path in the
        ``ADDONS`` setting. For each of these add-ons, the configuration will be
        read from the dictionary setting whose name matches the uppercase add-on
        name.

        :param settings: The :class:`~scrapy.settings.Settings` object from \
            which to read the add-on configuration
        :type settings: :class:`~scrapy.settings.Settings`
        """
        paths = build_component_list(settings['ADDONS'])
        addons = [self.get_addon(path) for path in paths]
        configs = [settings.getdict(addon.name.upper()) for addon in addons]
        for a, c in zip(addons, configs):
            self.add(a, c)

    def check_dependency_clashes(self):
        """Check for incompatibilities in add-on dependencies.

        Add-ons can provide information about their dependencies in their
        ``provides``, ``modifies`` and ``requires`` attributes. This method will
        raise an ``ImportError`` if

        * a component required by an add-on is not provided by any other add-on,
          or
        * a component modified by an add-on is not provided by any other add-on,
          or
        * the same component is provided by more than one add-on,

        and warn when a component required by an add-on is modified by any other
        add-on.
        """
        # Collect all active add-ons and the components they provide
        ws = WorkingSet('')
        def add_dist(project_name, version, **kwargs):
            if project_name in ws.entry_keys.get('scrapy', []):
                raise ImportError("Component {} provided by multiple add-ons"
                                  "".format(project_name))
            else:
                dist = Distribution(project_name=project_name, version=version,
                                    **kwargs)
                ws.add(dist, entry='scrapy')
        for name in self:
            ver = self[name].version
            add_dist(name, ver)
            for provides_name in getattr(self[name], 'provides', []):
                add_dist(provides_name, ver)

        # Collect all required and modified components
        def compile_attribute_dict(attribute_name):
            attrs = defaultdict(list)
            for name in self:
                for entry in getattr(self[name], attribute_name, []):
                    attrs[entry].append(name)
            return attrs
        modified = compile_attribute_dict('modifies')
        required = compile_attribute_dict('requires')

        req_or_mod = set(required.keys()).union(modified.keys())
        for reqstr in req_or_mod:
            req = Requirement.parse(reqstr)
            # May raise VersionConflict. Do we want to catch it and raise
            # our own exception or is it helpful enough?
            if ws.find(req) is None:
                raise ImportError(
                          "Add-ons {} require or modify missing component {}"
                          "".format(required[reqstr]+modified[reqstr], reqstr))

        mod_and_req = set(required.keys()).intersection(modified.keys())
        for conflict in mod_and_req:
            warnings.warn("Component '{}', required by add-ons {}, is modified "
                          "by add-ons {}".format(conflict, required[conflict],
                                                 modified[conflict]))

    def disable(self, addon):
        """Disable an add-on, i.e. prevent its callbacks from being called.

        If you disable an add-on before it is loaded, it will be disabled as
        soon as it is added to the :class:`AddonManager`.

        :param addon: Name of the add-on to be disabled
        :type addon: ``str``
        """
        if addon in self:
            self.configs[addon]['_enabled'] = False
        else:
            self._disable_on_add.append(addon)

    def enable(self, addon):
        """Re-enable a disabled add-on.

        Will raise ``ValueError`` if the add-on is neither already loaded nor
        marked for being disabled on adding.

        :param addon: Name of the add-on to be enabled
        :type addon: ``str``
        """
        if addon in self:
            self.configs[addon]['_enabled'] = True
        elif addon in self._disable_on_add:
            self._disable_on_add.remove(addon)
        else:
            raise ValueError("Add-ons need to be added before they can be "
                             "enabled")

    @property
    def disabled(self):
        """Names of disabled add-ons"""
        return ([a for a in self if not self.configs[a].get('_enabled', True)] +
                self._disable_on_add)

    @property
    def enabled(self):
        """Names of enabled add-ons"""
        return [a for a in self if self.configs[a].get('_enabled', True)]

    def _call_if_exists(self, obj, cbname, *args, **kwargs):
        if obj is None:
            return
        try:
            cb = getattr(obj, cbname)
        except AttributeError:
            return
        else:
            cb(*args, **kwargs)

    def _call_addon(self, addonname, cbname, *args, **kwargs):
        if self.configs[addonname].get('_enabled', True):
            self._call_if_exists(self[addonname], cbname,
                                 self.configs[addonname], *args, **kwargs)

    def update_addons(self):
        """Call ``update_addons()`` of all held add-ons.

        This will also call ``update_addons()`` of all add-ons that are added
        last minute during the ``update_addons()`` routine of other add-ons.
        """
        called_addons = set()
        while called_addons != set(self):
            for name in set(self).difference(called_addons):
                called_addons.add(name)
                self._call_addon(name, 'update_addons', self)

    def update_settings(self, settings):
        """Call ``update_settings()`` of all held add-ons.

        :param settings: The :class:`~scrapy.settings.Settings` object to be \
            updated
        :type settings: :class:`~scrapy.settings.Settings`
        """
        for name in self:
            self._call_addon(name, 'update_settings', settings)

    def check_configuration(self, crawler):
        """Call ``check_configuration()`` of all held add-ons.

        :param crawler: the fully-initialized crawler
        :type crawler: :class:`~scrapy.crawler.Crawler`
        """
        for name in self:
            self._call_addon(name, 'check_configuration', crawler)


from scrapy.addons.builtins import *
