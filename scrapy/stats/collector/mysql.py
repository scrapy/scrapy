"""
A Stats collector for persisting stats (pickled) to a MySQL db
"""

import cPickle as pickle
from datetime import datetime

from scrapy.stats.collector import StatsCollector
from scrapy.utils.db import mysql_connect
from scrapy.conf import settings

class MysqlStatsCollector(StatsCollector):

    def __init__(self):
        super(MysqlStatsCollector, self).__init__()
        mysqluri = settings['STATS_MYSQL_URI']
        self._mysql_conn = mysql_connect(mysqluri, use_unicode=False) if mysqluri else None
        
    def close_domain(self, domain, reason):
        if self._mysql_conn:
            stored = datetime.utcnow()
            datas = pickle.dumps(self._stats[domain])
            table = 'domain_data_history'

            c = self._mysql_conn.cursor()
            c.execute("INSERT INTO %s (domain,stored,data) VALUES (%%s,%%s,%%s)" % table, \
                (domain, stored, datas))
            self._mysql_conn.commit()
        super(MysqlStatsCollector, self).close_domain(domain, reason)
