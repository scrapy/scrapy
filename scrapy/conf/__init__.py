"""
Scrapy settings manager

See documentation in docs/topics/settings.rst
"""

import os
import cPickle as pickle

SETTINGS_DISABLED = os.environ.get('SCRAPY_SETTINGS_DISABLED', False)

class Settings(object):

    # settings in precedence order
    overrides = None
    settings_module = None
    defaults = None
    global_defaults = None

    def __init__(self):
        self.set_settings_module()
        pickled_settings = os.environ.get("SCRAPY_PICKLED_SETTINGS_TO_OVERRIDE")
        self.overrides = pickle.loads(pickled_settings) if pickled_settings else {}
        self.defaults = {}
        self.global_defaults = __import__('scrapy.conf.default_settings', {}, {}, [''])

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

    def set_settings_module(self, settings_module_path=None):
        if settings_module_path is None:
            settings_module_path = os.environ.get('SCRAPYSETTINGS_MODULE', \
                'scrapy_settings')
        self.settings_module_path = settings_module_path
        try:
            self.settings_module = __import__(settings_module_path, {}, {}, [''])
        except ImportError:
            self.settings_module = None

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

    def __str__(self):
        return "<Settings %r>" % self.settings_module_path

settings = Settings()
