from zope.interface import Interface, implements

from scrapy.xlib.pydispatch import dispatcher
from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import load_object
from scrapy.utils.sqlite import JsonSqliteDict
from scrapy.utils.project import sqlite_db
from scrapy import signals

class ISpiderContextStorage(Interface):

    def get(spider):
        """Get the context for the given spider, or None if the spider has no
        context stored."""

    def put(spider, context):
        """Store the context for the given spider"""


class SqliteSpiderContextStorage(object):

    implements(ISpiderContextStorage)
    sqlite_dict_class = JsonSqliteDict

    def __init__(self, database=None, table='contexts'):
        self.d = self.sqlite_dict_class(database, table)

    @classmethod
    def from_settings(cls, settings):
        return cls(sqlite_db(settings['SQLITE_DB']))

    def get(self, spider):
        if spider.name in self.d:
            return self.d[spider.name]

    def put(self, spider, context):
        self.d[spider.name] = context


class SpiderContext(object):

    def __init__(self, storage):
        dispatcher.connect(self._spider_opened, signals.spider_opened)
        dispatcher.connect(self._spider_closed, signals.spider_closed)
        self.storage = storage

    @classmethod
    def from_settings(cls, settings):
        if not settings.getbool('SPIDER_CONTEXT_ENABLED'):
            raise NotConfigured
        stcls = load_object(settings['SPIDER_CONTEXT_STORAGE_CLASS'])
        storage = stcls.from_settings(settings)
        return cls(storage)

    def _spider_opened(self, spider):
        spider.context = self.storage.get(spider) or {}

    def _spider_closed(self, spider):
        if spider.context:
            self.storage.put(spider, spider.context)

