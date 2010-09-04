import sqlite3

from zope.interface import implements

from scrapy import log
from scrapy.interfaces import ISpiderQueue
from scrapy.utils.sqlite import JsonSqlitePriorityQueue


class SqliteSpiderQueue(object):

    implements(ISpiderQueue)

    def __init__(self, database=None, table='spider_queue'):
        try:
            self.q = JsonSqlitePriorityQueue(database, table)
        except sqlite3.Error, e:
            self.q = JsonSqlitePriorityQueue(':memory:', table)
            log.msg("Cannot open SQLite %r - using in-memory spider queue " \
                "instead. Error was: %r" % (database, str(e)), log.WARNING)

    @classmethod
    def from_settings(cls, settings):
        return cls(settings['SQLITE_DB'])

    def add(self, name, **spider_args):
        d = spider_args.copy()
        d['name'] = name
        priority = float(d.pop('priority', 0))
        self.q.put(d, priority)

    def pop(self):
        return self.q.pop()

    def count(self):
        return len(self.q)

    def list(self):
        return [x[0] for x in self.q]

    def clear(self):
        self.q.clear()
