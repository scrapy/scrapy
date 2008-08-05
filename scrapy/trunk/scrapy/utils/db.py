"""
Function for dealing with databases
"""
import re

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

        d['charset'] = "utf8"
        d['reconnect'] = 1
        d.update(kwargs)
        return MySQLdb.connect(**d)
