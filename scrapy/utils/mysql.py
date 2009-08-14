"""Functions for dealing with databases"""

import re

import MySQLdb

from scrapy.core.engine import scrapyengine
from scrapy.conf import settings
from scrapy import log

mysql_uri_re = r"mysql:\/\/(?P<user>[^:]+)(:(?P<passwd>[^@]+))?@(?P<host>[^/:]+)(:(?P<port>\d+))?/(?P<db>.*)$"

def parse_uri(mysql_uri):
    """Parse mysql URI and return a dict with its parameters"""
    m = re.search(mysql_uri_re, mysql_uri)
    if m:
        d = m.groupdict()
        if d['passwd'] is None:
            del(d['passwd'])
        if d['port'] is None:
            del(d['port'])
        else:
            d['port'] = int(d['port'])
        return d

def mysql_connect(db_uri_or_dict, **kwargs):
    """Connects to a MySQL DB given a mysql URI"""
    if isinstance(db_uri_or_dict, dict):
        d = db_uri_or_dict
    else:
        d = parse_uri(db_uri_or_dict)
    if not d:
        return
    d.update(settings.get("MYSQL_CONNECTION_SETTINGS", {}))
    d.update(kwargs)
    log.msg("Connecting to MySQL: db=%r, host=%r, user=%r" % (d['db'], \
        d['host'], d['user']), level=log.DEBUG)
    conn = MySQLdb.connect(**d)

    # connection keep-alive
    def conn_ping():
        log.msg("Pinging connection to %s/%s" % (d['host'], d['db']), \
            level=log.DEBUG)
        conn.ping()
    ping_period = settings.getint("MYSQL_CONNECTION_PING_PERIOD")
    if ping_period:
        scrapyengine.addtask(conn_ping, ping_period)

    return conn
