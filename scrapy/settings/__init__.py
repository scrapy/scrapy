import six
import json

from . import default_settings


SETTINGS_PRIORITIES = {
    'default': 0,
    'command': 10,
    'project': 20,
    'cmdline': 40,
}


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
        for name, defvalue in iter_default_settings():
            self.set(name, defvalue, 'default')
        if values is not None:
            self.setdict(values, priority)

    def __getitem__(self, opt_name):
        value = None
        if opt_name in self.attributes:
            value = self.attributes[opt_name].value
        return value

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
        value = self.get(name)
        if value is None:
            return default or []
        elif hasattr(value, '__iter__'):
            return value
        else:
            return str(value).split(',')

    def getdict(self, name, default=None):
        value = self.get(name)
        if value is None:
            return default or {}
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


class CrawlerSettings(Settings):

    def __init__(self, settings_module=None, **kw):
        super(CrawlerSettings, self).__init__(**kw)
        self.settings_module = settings_module
        self.overrides = {}
        self.defaults = {}

    def __getitem__(self, opt_name):
        if opt_name in self.overrides:
            return self.overrides[opt_name]
        if self.settings_module and hasattr(self.settings_module, opt_name):
            return getattr(self.settings_module, opt_name)
        if opt_name in self.defaults:
            return self.defaults[opt_name]
        return super(CrawlerSettings, self).__getitem__(opt_name)

    def __str__(self):
        return "<CrawlerSettings module=%r>" % self.settings_module


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
