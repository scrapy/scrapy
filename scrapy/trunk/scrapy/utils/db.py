"""
Function for dealing with databases
"""
import re
from scrapy.conf import settings
from scrapy.core import log
from scrapy.core.engine import scrapyengine

def mysql_connect(db_uri, **kwargs):
    """
    Connects to a MySQL DB given a mysql URI
    """
    import MySQLdb

    if not db_uri or not db_uri.startswith('mysql://'):
        raise Exception("Incorrect MySQL URI: %s" % db_uri)
    m = re.search(r"mysql:\/\/(?P<user>[^:]+)(:(?P<passwd>[^@]+))?@(?P<host>[^/]+)/(?P<db>.*)$", db_uri)
    if m:
        d = m.groupdict()
        if d['passwd'] is None:
            del(d['passwd'])

        d.update(settings.get("MYSQL_CONNECTION_SETTINGS"))
        d.update(kwargs)
        
        dcopy = d.copy()
        if dcopy.get("passwd"):
            dcopy["passwd"] = "********"
        log.msg("Connecting db with settings %s" % dcopy )
        
        conn = MySQLdb.connect(**d)
        
        #this is to maintain active the connection
        def _ping():
            log.msg("Pinging connection to %s/%s" % (d.get('host'), d.get('db')) )
            conn.ping()
        scrapyengine.addtask(_ping, settings.getint("MYSQL_CONNECTION_PING_PERIOD", 600))
        
        return conn