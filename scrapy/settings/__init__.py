import json
from . import default_settings


class Settings(object):

    def __init__(self, values=None):
        self.values = values.copy() if values else {}
        self.global_defaults = default_settings

    def __getitem__(self, opt_name):
        if opt_name in self.values:
            return self.values[opt_name]
        return getattr(self.global_defaults, opt_name, None)

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
        if isinstance(value, basestring):
            value = json.loads(value)
        if isinstance(value, dict):
            return value
        raise ValueError("Cannot convert value for setting '%s' to dict: '%s'" % (name, value))

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
