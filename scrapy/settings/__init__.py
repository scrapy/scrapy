import six
import json
import warnings
from collections import MutableMapping
from importlib import import_module

from scrapy.utils.deprecate import create_deprecated_class
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning

from scrapy.settings import default_settings


SETTINGS_PRIORITIES = {
    'default': 0,
    'command': 10,
    'project': 20,
    'cmdline': 40,
}


_NO_SET = object()


class SettingsAttribute(object):

    """Class for storing data related to settings attributes.

    This class is intended for internal usage, you should try Settings class
    for settings configuration, not this one.
    """

    def __init__(self, value, priority):
        self.value = value
        self.priority = priority

    def set(self, value, priority):
        """Sets value if priority is higher or equal than current priority."""
        if priority >= self.priority:
            self.value = value
            self.priority = priority

    def __str__(self):
        return "<SettingsAttribute value={self.value!r} " \
               "priority={self.priority}>".format(self=self)

    __repr__ = __str__


class Settings(object):

    def __init__(self, values=None, priority='project'):
        self.attributes = {}
        self.setmodule(default_settings, priority='default')
        if values is not None:
            self.setdict(values, priority)

    def __getitem__(self, opt_name):
        value = None
        if opt_name in self.attributes:
            value = self.attributes[opt_name].value
        return value

    def _get_default(self, value, default, required):
        if not required and value is _NO_SET:
            return default
        return value

    def get(self, name, default=_NO_SET, required=False):
        value = default if name not in self.attributes else self[name]
        if required and value is _NO_SET:
            raise NotConfigured
        return None if value is _NO_SET else value

    def getbool(self, name, default=_NO_SET, required=False):
        """
        True is: 1, '1', True
        False is: 0, '0', False, None
        """
        return bool(int(self.get(name, self._get_default(default, False, required), required)))

    def getint(self, name, default=_NO_SET, required=False):
        return int(self.get(name, self._get_default(default, 0, required), required))

    def getfloat(self, name, default=_NO_SET, required=False):
        return float(self.get(name, self._get_default(default, 0.0, required), required))

    def getlist(self, name, default=_NO_SET, required=False):
        value = self.get(name, self._get_default(default, [], required), required)
        if value is None:
            return []
        elif hasattr(value, '__iter__'):
            return value
        else:
            return str(value).split(',')

    def getdict(self, name, default=_NO_SET, required=False):
        value = self.get(name, self._get_default(default, {}, required), required)
        if value is None:
            return {}
        if isinstance(value, six.string_types):
            value = json.loads(value)
        if isinstance(value, dict):
            return value
        raise ValueError("Cannot convert value for setting '%s' to dict: '%s'" % (name, value))

    def set(self, name, value, priority='project'):
        if isinstance(priority, six.string_types):
            priority = SETTINGS_PRIORITIES[priority]
        if name not in self.attributes:
            self.attributes[name] = SettingsAttribute(value, priority)
        else:
            self.attributes[name].set(value, priority)

    def setdict(self, values, priority='project'):
        for name, value in six.iteritems(values):
            self.set(name, value, priority)

    def setmodule(self, module, priority='project'):
        if isinstance(module, six.string_types):
            module = import_module(module)
        for key in dir(module):
            if key.isupper():
                self.set(key, getattr(module, key), priority)

    @property
    def overrides(self):
        warnings.warn("`Settings.overrides` attribute is deprecated and won't "
                      "be supported in Scrapy 0.26, use "
                      "`Settings.set(name, value, priority='cmdline')` instead",
                      category=ScrapyDeprecationWarning, stacklevel=2)
        try:
            o = self._overrides
        except AttributeError:
            self._overrides = o = _DictProxy(self, 'cmdline')
        return o

    @property
    def defaults(self):
        warnings.warn("`Settings.defaults` attribute is deprecated and won't "
                      "be supported in Scrapy 0.26, use "
                      "`Settings.set(name, value, priority='default')` instead",
                      category=ScrapyDeprecationWarning, stacklevel=2)
        try:
            o = self._defaults
        except AttributeError:
            self._defaults = o = _DictProxy(self, 'default')
        return o


class _DictProxy(MutableMapping):

    def __init__(self, settings, priority):
        self.o = {}
        self.settings = settings
        self.priority = priority

    def __len__(self):
        return len(self.o)

    def __getitem__(self, k):
        return self.o[k]

    def __setitem__(self, k, v):
        self.settings.set(k, v, priority=self.priority)
        self.o[k] = v

    def __delitem__(self, k):
        del self.o[k]

    def __iter__(self, k, v):
        return iter(self.o)


class CrawlerSettings(Settings):

    def __init__(self, settings_module=None, **kw):
        Settings.__init__(self, **kw)
        self.settings_module = settings_module

    def __getitem__(self, opt_name):
        if opt_name in self.overrides:
            return self.overrides[opt_name]
        if self.settings_module and hasattr(self.settings_module, opt_name):
            return getattr(self.settings_module, opt_name)
        if opt_name in self.defaults:
            return self.defaults[opt_name]
        return Settings.__getitem__(self, opt_name)

    def __str__(self):
        return "<CrawlerSettings module=%r>" % self.settings_module

CrawlerSettings = create_deprecated_class(
    'CrawlerSettings', CrawlerSettings,
    new_class_path='scrapy.settings.Settings')


def iter_default_settings():
    """Return the default settings as an iterator of (name, value) tuples"""
    for name in dir(default_settings):
        if name.isupper():
            yield name, getattr(default_settings, name)

def overridden_settings(settings):
    """Return a dict of the settings that have been overridden"""
    for name, defvalue in iter_default_settings():
        value = settings[name]
        if not isinstance(defvalue, dict) and value != defvalue:
            yield name, value
