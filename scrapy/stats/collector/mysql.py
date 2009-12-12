"""
A Stats collector for persisting stats (pickled) to a MySQL db
"""

import cPickle as pickle
from datetime import datetime

from scrapy.stats.collector import StatsCollector
from scrapy.utils.mysql import mysql_connect
from scrapy.conf import settings

class MysqlStatsCollector(StatsCollector):

    def __init__(self):
        super(MysqlStatsCollector, self).__init__()
        mysqluri = settings['STATS_MYSQL_URI']
        self._mysql_conn = mysql_connect(mysqluri, use_unicode=False) if mysqluri else None
        
    def _persist_stats(self, stats, spider=None):
        if spider is None: # only store spider-specific stats
            return
        if self._mysql_conn is None:
            return
        stored = datetime.utcnow()
        datas = pickle.dumps(stats)
        table = 'domain_data_history'

        c = self._mysql_conn.cursor()
        c.execute("INSERT INTO %s (domain,stored,data) VALUES (%%s,%%s,%%s)" % table, \
            (spider.domain_name, stored, datas))
        self._mysql_conn.commit()
