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


class SpiderSettings(Settings):

    def __init__(self, spider, crawler_settings, **kw):
        super(SpiderSettings, self).__init__(**kw)
        self.spider = spider
        self.cset = crawler_settings

    def __getitem__(self, opt_name):
        if opt_name in self.cset.overrides:
            return self.cset.overrides[opt_name]
        if hasattr(self.spider, opt_name):
            return getattr(self.spider, opt_name)
        if self.cset.settings_module and hasattr(self.cset.settings_module, opt_name):
            return getattr(self.cset.settings_module, opt_name)
        if opt_name in self.cset.defaults:
            return self.cset.defaults[opt_name]
        return super(SpiderSettings, self).__getitem__(opt_name)

    def __str__(self):
        return "<SpiderSettings spider=%r>" % self.spider.name
