import os, pickle

SETTINGS_MODULE = os.environ.get('SCRAPYSETTINGS_MODULE', 'scrapy_settings')

class Settings(object):
    """Class to obtain configuration values from settings module
       which can be overriden by environment variables prepended by SCRAPY_"""

    # settings in precedence order
    overrides = None
    settings = None
    defaults = None
    core = None

    def __init__(self):
        pickled_settings = os.environ.get("SCRAPY_PICKLED_SETTINGS")
        self.overrides = pickle.loads(pickled_settings) if pickled_settings else {}
        self.settings = self._import(SETTINGS_MODULE)
        self.defaults = {}
        self.core = self._import('scrapy.conf.core_settings')

    def _import(self, modulepath):
        try:
            return __import__(modulepath, {}, {}, [''])
        except ImportError:
            import sys
            err = "Error: Can't find %s module in your python path\n"
            sys.stderr.write(err % modulepath)
            sys.exit(1)

    def __getitem__(self, opt_name):
        if opt_name in self.overrides:
            return self.overrides[opt_name]

        if 'SCRAPY_' + opt_name in os.environ:
            return os.environ['SCRAPY_' + opt_name]

        if hasattr(self.settings, opt_name):
            return getattr(self.settings, opt_name)

        if opt_name in self.defaults:
            return self.defaults[opt_name]

        if hasattr(self.core, opt_name):
            return getattr(self.core, opt_name)

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
