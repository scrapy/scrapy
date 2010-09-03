import pkgutil
from cStringIO import StringIO
from ConfigParser import SafeConfigParser, NoSectionError, NoOptionError

from scrapy.utils.conf import get_sources

class Config(object):
    """A ConfigParser wrapper to support defaults when calling instance
    methods, and also tied to a single section"""

    SOURCES = ['scrapyd.cfg', '/etc/scrapyd.cfg']
    SECTION = 'scrapyd'

    def __init__(self):
        sources = self.SOURCES + get_sources()
        default_config = pkgutil.get_data(__package__, 'default_scrapyd.cfg')
        self.cp = SafeConfigParser()
        self.cp.readfp(StringIO(default_config))
        self.cp.read(sources)

    def _getany(self, method, option, default):
        try:
            return method(self.SECTION, option)
        except (NoSectionError, NoOptionError):
            if default is not None:
                return default
            raise

    def get(self, option, default=None):
        return self._getany(self.cp.get, option, default)

    def getint(self, option, default=None):
        return self._getany(self.cp.getint, option, default)

    def getfloat(self, option, default=None):
        return self._getany(self.cp.getfloat, option, default)

    def getboolean(self, option, default=None):
        return self._getany(self.cp.getboolean, option, default)
