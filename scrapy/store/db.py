"""
Store implementations using a MySQL DB
"""
import cPickle as pickle
from datetime import datetime

from scrapy.utils.misc import stats_getpath
from scrapy.utils.db import mysql_connect

class DomainDataHistory(object):
    """
    This is a store for domain data, with history.
    """

    def __init__(self, db_uri, table_name):
        self.db_uri = db_uri
        self._mysql_conn = None
        self._table = table_name

    def get_mysql_conn(self):
        if self._mysql_conn is None:
            self._mysql_conn = mysql_connect(self.db_uri, use_unicode=False)
        return self._mysql_conn
    mysql_conn = property(get_mysql_conn)

    def get(self, domain, count=1, offset=0, stored_after=None, stored_before=None, path=None):
        """
        Get the last records stored for the given domain. 
        If count is given that number of records is retunred, otherwise all records.
        If stored_{after,before} is given the results are restricted to that time interval.
        The result is a list of tuples: (timestamp, data)
        If path is given it only returns stats of that given path (only for dict objects like stats)
        """
        sqlsuf = ""
        if count is not None:
            sqlsuf += "LIMIT %d " % count
        if offset:
            sqlsuf += "OFFSET %d " % offset
        filter = ""
        if stored_after:
            filter += "AND stored>='%s'" % stored_after.strftime("%Y-%m-%d %H:%M:%S")
        if stored_before:
            filter += "AND stored<='%s'" % stored_before.strftime("%Y-%m-%d %H:%M:%S")

        c = self.mysql_conn.cursor()
        select = "SELECT stored,data FROM %s WHERE domain=%%s %s ORDER BY stored DESC %s" % (self._table, filter, sqlsuf)
        c.execute(select, domain)
        for stored, datas in c:
            obj = pickle.loads(datas)
            if path and isinstance(obj, dict):
                yield stored, stats_getpath(obj, path)
            else:
                yield stored, obj

    def getlast(self, domain, offset=0, path=None):
        """
        Get the Nth last data stored for the given domain
        If offset=0 get the last data stored
        If offset=1 get the previous data stored
        ...and so on
        """
        datal = list(self.get(domain, count=1, offset=offset, path=path))
        if datal:
            return datal[0]
        
    def getall(self, domain, path=None):
        """
        Get all data stored for the given domain as a list of tuples:
        (stored, timestamp)
        """
        return self.get(domain, count=None, path=path)

    def getlast_alldomains(self, count=None, offset=None, order='domain', olist='ASC', path=None):
        """
        Get all last data for all domains as a list of tuples, unless
        data is sliced by count and offset values.
        Ordered by domain is the default.
        TODO: This could be merged with: get(domain=None, ..., +order)

        Return a list of tuples (domain, timestamp, data)
        """
        sqlsuf = ""
        if count is not None:
            sqlsuf += "LIMIT %s " % count
        if offset:
            sqlsuf += "OFFSET %s " % offset
        
        c = self.mysql_conn.cursor()
        select = "SELECT domain, MAX(stored) as stored, data \
                  FROM ( \
                    SELECT * FROM %s ORDER BY stored DESC \
                  ) AS inner_ordered \
                  GROUP BY domain \
                  ORDER BY %s %s %s" % (self._table, order, olist, sqlsuf)
        c.execute(select)
        for domain, stored, datas in c:
            obj = pickle.loads(datas)
            if path and isinstance(obj, dict):
                yield domain, stored, stats_getpath(obj, path)
            else:
                yield domain, stored, obj

    def domain_count(self):
        """
        Return the number of domains stored in the database
        """
        c = self.mysql_conn.cursor()
        c.execute("SELECT COUNT(DISTINCT(domain)) FROM %s" % self._table)
        return c.fetchone()[0]

    def put(self, domain, data, timestamp=None):
        """
        Store data in history using the given timestamp (or now if omitted).
        data can be any pickable object
        """
        stored = timestamp if timestamp else datetime.now()
        datas = pickle.dumps(data)

        c = self.mysql_conn.cursor()
        c.execute("INSERT INTO %s (domain,stored,data) VALUES (%%s,%%s,%%s)" % self._table, (domain, stored, datas))
        self.mysql_conn.commit()

    def remove(self, domain):
        """
        Remove all data stored for the given domain
        """
        c = self.mysql_conn.cursor()
        c.execute("DELETE FROM %s WHERE domain=%%s" % self._table, domain)
        self.mysql_conn.commit()

