"""
Scrapy settings manager

See documentation in docs/topics/settings.rst
"""

import os
import cPickle as pickle

SETTINGS_MODULE = os.environ.get('SCRAPYSETTINGS_MODULE', 'scrapy_settings')
SETTINGS_DISABLED = os.environ.get('SCRAPY_SETTINGS_DISABLED', False)

class Settings(object):

    # settings in precedence order
    overrides = None
    settings_module = None
    defaults = None
    global_defaults = None

    def __init__(self):
        pickled_settings = os.environ.get("SCRAPY_PICKLED_SETTINGS_TO_OVERRIDE")
        self.overrides = pickle.loads(pickled_settings) if pickled_settings else {}
        self.settings_module = self._import(SETTINGS_MODULE)
        self.defaults = {}
        self.global_defaults = self._import('scrapy.conf.default_settings')

    def _import(self, modulepath):
        try:
            return __import__(modulepath, {}, {}, [''])
        except ImportError:
            pass

    def __getitem__(self, opt_name):
        if not SETTINGS_DISABLED:
            if opt_name in self.overrides:
                return self.overrides[opt_name]
            if 'SCRAPY_' + opt_name in os.environ:
                return os.environ['SCRAPY_' + opt_name]
            if hasattr(self.settings_module, opt_name):
                return getattr(self.settings_module, opt_name)
            if opt_name in self.defaults:
                return self.defaults[opt_name]
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
            return []
        elif hasattr(value, '__iter__'):
            return value
        else:
            return str(value).split(',')

settings = Settings()
