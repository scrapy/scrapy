"""
SQLHistoryStore

Persistent history storage using relational database
"""
from scrapy.contrib.history.history import URLHistory
from scrapy.core import log
from scrapy.conf import settings

class SQLHistoryStore(object) :
    """Implementation of a data store that stores information in a relation 
    database

    This maintains a URLHistory object per site. That means each domain
    has it's own session and is isolated from the others.
    """
    
    def __init__(self):
        self._store = {}
        self._dbinfo = settings['SCRAPING_DB']
        self._debug = settings['DEBUG_SQL_HISTORY_STORE']
   
    def open(self, site):
        self._store[site] = URLHistory(self._dbinfo)

    def close_site(self, site):
        self._store[site].close()
        del self._store[site]
    
    def store(self, site, key, url, parent=None, version=None, post_version=None):
        history = self._store[site]
        if self._debug:
            log.msg("record_version(key=%s, url=%s, parent=%s, version=%s, post_version=%s)" % 
                    (key, url, parent, version, post_version), domain=site, level=log.DEBUG)
        history.record_version(key, url, parent, version, post_version)

    def has_site(self, site):
        return site in self._store

    def status(self, site, key):
        if site in self._store:
            history = self._store[site]
            return history.get_url_status(key)

    def version_info(self, site, version):
        history = self._store[site]
        return history.get_version_info(version)
