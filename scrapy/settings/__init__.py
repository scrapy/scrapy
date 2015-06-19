import six
import json
import copy
import warnings
from collections import Mapping, MutableMapping
from importlib import import_module

from scrapy.utils.deprecate import create_deprecated_class
from scrapy.exceptions import ScrapyDeprecationWarning

from . import default_settings


SETTINGS_PRIORITIES = {
    'default': 0,
    'command': 10,
    'project': 20,
    'spider': 30,
    'cmdline': 40,
}

def get_settings_priority(priority):
    if isinstance(priority, six.string_types):
        return SETTINGS_PRIORITIES[priority]
    else:
        return priority


class SettingsAttribute(object):

    """Class for storing data related to settings attributes.

    This class is intended for internal usage, you should try Settings class
    for settings configuration, not this one.
    """

    def __init__(self, value, priority):
        self.value = value
        if isinstance(self.value, BaseSettings):
            self.priority = max(self.value.maxpriority(), priority)
        else:
            self.priority = priority

    def set(self, value, priority):
        """Sets value if priority is higher or equal than current priority."""
        if isinstance(self.value, BaseSettings):
            # Ignore self.priority if self.value has per-key priorities
            self.value.update(value, priority)
            self.priority = max(self.value.maxpriority(), priority)
        else:
            if priority >= self.priority:
                self.value = value
                self.priority = priority

    def __str__(self):
        return "<SettingsAttribute value={self.value!r} " \
               "priority={self.priority}>".format(self=self)

    __repr__ = __str__


class BaseSettings(MutableMapping):

    def __init__(self, values=None, priority='project'):
        self.frozen = False
        self.attributes = {}
        self.update(values, priority)

    def __getitem__(self, opt_name):
        value = None
        if opt_name in self:
            value = self.attributes[opt_name].value
        return value

    def __contains__(self, name):
        return name in self.attributes

    def get(self, name, default=None):
        return self[name] if self[name] is not None else default

    def getbool(self, name, default=False):
        """
        True is: 1, '1', True
        False is: 0, '0', False, None
        """
        return bool(int(self.get(name, default)))

    def getint(self, name, default=0):
        return int(self.get(name, default))

    def getfloat(self, name, default=0.0):
        return float(self.get(name, default))

    def getlist(self, name, default=None):
        value = self.get(name, default or [])
        if isinstance(value, six.string_types):
            value = value.split(',')
        return list(value)

    def getdict(self, name, default=None):
        value = self.get(name, default or {})
        if isinstance(value, six.string_types):
            value = json.loads(value)
        return dict(value)

    def _getcomposite(self, name):
        # DO NOT USE THIS FUNCTION IN YOUR CUSTOM PROJECTS
        # It's for internal use in the transition away from the _BASE settings and
        # will be removed along with _BASE support in a future release
        basename = name + "_BASE"
        if basename in self:
            warnings.warn('_BASE settings are deprecated.',
                          category=ScrapyDeprecationWarning)
            compsett = BaseSettings(self[name + "_BASE"], priority='default')
            compsett.update(self[name])
            return compsett
        else:
            return self[name]

    def getpriority(self, name):
        prio = None
        if name in self:
            prio = self.attributes[name].priority
        return prio

    def maxpriority(self):
        if len(self) > 0:
            return max(self.getpriority(name) for name in self)
        else:
            return get_settings_priority('default')

    def __setitem__(self, name, value):
        self.set(name, value)

    def set(self, name, value, priority='project'):
        self._assert_mutability()
        priority = get_settings_priority(priority)
        if name not in self:
            if isinstance(value, SettingsAttribute):
                self.attributes[name] = value
            else:
                self.attributes[name] = SettingsAttribute(value, priority)
        else:
            self.attributes[name].set(value, priority)

    def setdict(self, values, priority='project'):
        self.update(values, priority)

    def setmodule(self, module, priority='project'):
        self._assert_mutability()
        if isinstance(module, six.string_types):
            module = import_module(module)
        for key in dir(module):
            if key.isupper():
                self.set(key, getattr(module, key), priority)

    def update(self, values, priority='project'):
        self._assert_mutability()
        if isinstance(values, six.string_types):
            values = json.loads(values)
        if values is not None:
            if isinstance(values, BaseSettings):
                for name, value in six.iteritems(values):
                    self.set(name, value, values.getpriority(name))
            else:
                for name, value in six.iteritems(values):
                    self.set(name, value, priority)

    def delete(self, name, priority='project'):
        self._assert_mutability()
        priority = get_settings_priority(priority)
        if priority >= self.getpriority(name):
            del self.attributes[name]

    def __delitem__(self, name):
        self._assert_mutability()
        del self.attributes[name]

    def _assert_mutability(self):
        if self.frozen:
            raise TypeError("Trying to modify an immutable Settings object")

    def copy(self):
        return copy.deepcopy(self)

    def freeze(self):
        self.frozen = True

    def frozencopy(self):
        copy = self.copy()
        copy.freeze()
        return copy

    def __iter__(self):
        return iter(self.attributes)

    def __len__(self):
        return len(self.attributes)

    def __str__(self):
        return str(self.attributes)

    __repr__ = __str__

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


class Settings(BaseSettings):

    def __init__(self, values=None, priority='project'):
        # Do not pass kwarg values here. We don't want to promote user-defined
        # dicts, and we want to update, not replace, default dicts with the
        # values given by the user
        super(Settings, self).__init__()
        self.setmodule(default_settings, 'default')
        # Promote default dictionaries to BaseSettings instances for per-key
        # priorities
        for name in self:
            val = self[name]
            if isinstance(val, dict):
                self.set(name, BaseSettings(val, 'default'), 'default')
        self.update(values, priority)


class CrawlerSettings(Settings):

    def __init__(self, settings_module=None, **kw):
        self.settings_module = settings_module
        Settings.__init__(self, **kw)

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
