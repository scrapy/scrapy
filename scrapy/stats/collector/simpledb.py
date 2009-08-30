"""
A Stats collector for persisting stats to Amazon SimpleDB.

Requires the boto library: http://code.google.com/p/boto/
"""

from datetime import datetime

from boto import connect_sdb
from twisted.internet import threads

from scrapy.stats.collector import StatsCollector
from scrapy import log
from scrapy.conf import settings


class SimpledbStatsCollector(StatsCollector):

    def __init__(self):
        super(SimpledbStatsCollector, self).__init__()
        self._sdbdomain = settings['STATS_SDB_DOMAIN']
        self._async = settings.getbool('STATS_SDB_ASYNC')
        connect_sdb().create_domain(self._sdbdomain)

    def _persist_stats(self, stats, domain=None):
        if domain is None: # only store domain-specific stats
            return
        if not self._sdbdomain:
            return
        if self._async:
            dfd = threads.deferToThread(self._persist_to_sdb, domain, stats.copy())
            dfd.addErrback(log.err, 'Error uploading stats to SimpleDB', \
                domain=domain)
        else:
            self._persist_to_sdb(domain, stats)

    def _persist_to_sdb(self, domain, stats):
        ts = self._get_timestamp(domain).isoformat()
        sdb_item_id = "%s_%s" % (domain, ts)
        sdb_item = dict((k, self._to_sdb_value(v, k)) for k, v in stats.iteritems())
        sdb_item['domain'] = domain
        sdb_item['timestamp'] = self._to_sdb_value(ts)
        connect_sdb().put_attributes(self._sdbdomain, sdb_item_id, sdb_item)

    def _get_timestamp(self, domain):
        return datetime.utcnow()

    def _to_sdb_value(self, obj, ref=None):
        if isinstance(obj, bool):
            return u'%d' % obj
        elif isinstance(obj, (int, long)):
            return "%016d" % obj
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, basestring):
            return obj
        elif obj is None:
            return u''
        else:
            raise TypeError("%s unsupported type '%s' referenced as '%s'" % \
                (type(self).__name__, type(obj).__name__, ref))
