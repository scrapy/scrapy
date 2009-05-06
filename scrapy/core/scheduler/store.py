"""
The datastore module contains implementations of data storage engines for the
crawling process. These are used to track metrics on each site and on each
page visited.
"""
from datetime import datetime

class MemoryStore(object) :
    """Simple implementation of a data store. This is useful if no persistent 
    history is required (e.g. unit testing or development) and provides a 
    simpler reference implementation.
    """
    def __init__(self) :
        """The store will just be a dict with an entry for each site, that 
        entry will contain dicts and lists of data.
        """
        self._store = {}

    def open(self, site):
        self._store[site] = {}

    def close_site(self, site):
        del self._store[site]

    def store(self, site, key, url, parent=None, version=None, post_version=None):
        checked = datetime.now()
        self._store[key] = (version, checked)

    def status(self, site, key):
        """Get the version and last checked time for a key.

        this will be changed later to support checking (lazily) the last modified 
        time and perhaps other statistics needed by the scheduling algorithms
        """
        return self._store.get(key)
