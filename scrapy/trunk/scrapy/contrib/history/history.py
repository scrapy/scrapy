"""
History management
"""
import re
from datetime import datetime

import MySQLdb

class History(object):
    """Base class for tracking different kinds of histories"""
    
    def __init__(self, db_uri):
        self.db_uri = db_uri
        self._mysql_conn = None

    def connect(self):
        """
        Connect to PDB and open mysql connect to PRODUCT_DB
        """
        m = re.search(r"mysql:\/\/(?P<user>[^:]+)(:(?P<passwd>[^@]+))?@(?P<host>[^/]+)/(?P<db>.*)$", self.db_uri)
        if m:
            d = m.groupdict()
            if d['passwd'] is None:
                del(d['passwd'])

            d['charset'] = "utf8"
            self._mysql_conn = MySQLdb.connect(**d)

    def get_mysql_conn(self):
        if self._mysql_conn is None:
            self.connect()
        return self._mysql_conn
    mysql_conn = property(get_mysql_conn)


class ItemHistory(History):
    """
    Class instance registers item guids, and versions with check_item method.
    It also gives access to stored ItemTicket and ItemVersion objects.
    """
    NEW = 0
    UPDATE = 1
    DUPLICATE = 2
    
    def check_item(self, domain, item):
        """
        Store item's guid and version to the database along
        with date and time of last occurence.
        Return:
         * ItemHistory.NEW       - if guid hasn't been met
         * ItemHistory.UPDATE    - if history already contains guid, but versions doesn't match
         * ItemHistory.DUPLICATE - both guid and version are not new
        """
        version = item.version

        c = self.mysql_conn.cursor(MySQLdb.cursors.DictCursor)

        def add_version(version):
            insert = "INSERT INTO version (guid, version, seen) VALUES (%s,%s,%s)"
            c.execute(insert, (item.guid, version, datetime.now()))

        select = "SELECT * FROM ticket WHERE guid=%s"
        c.execute(select, item.guid)
        r = c.fetchone()
        if r:
            select = "SELECT * FROM version WHERE version=%s"
            if c.execute(select, version):
                update = "UPDATE version SET seen=%s WHERE version=%s"
                c.execute(update, (datetime.now(), version))
                self.mysql_conn.commit()
                return ItemHistory.DUPLICATE
            else:
                add_version(version)
                self.mysql_conn.commit()
                return ItemHistory.UPDATE
        else:
            insert = "INSERT INTO ticket (guid, domain, url, url_hash) VALUES (%s,%s,%s,%s)"
            c.execute(insert, (item.guid, domain, item.url, hash(item.url)))
            add_version(version)
            self.mysql_conn.commit()
            return ItemHistory.NEW
        
    def get_ticket(self, guid):
        """
        Return ItemTicket object for guid. 
        ItemVersion objects can be accessed via 'versions' list.
        """
        c = self.mysql_conn.cursor(MySQLdb.cursors.DictCursor)
        select = "SELECT * FROM ticket WHERE guid=%s"
        c.execute(select, guid)
        ticket = c.fetchone()
        if not ticket:
            raise Exception("Item ticket with guid = '%s' not found" % guid)
        ticket['versions'] = []
        select = "SELECT * FROM version WHERE guid=%s"
        c.execute(select, guid)
        for version in c.fetchall():
            ticket['versions'].append(version)
        return ticket

    def delete_ticket(self, guid):
        """Delete item ticket and associated versions from DB"""
        c = self.mysql_conn.cursor()
        delete = "DELETE FROM ticket WHERE guid=%s"
        c.execute(delete, guid)
        self.mysql_conn.commit()


class URLHistory(History):
    """
    Access URL status and history for the scraping engine
    
    This is degsigned to have an instance per domain where typically
    a call will be made to get_url_status, followed by either
    update_checked or record_version.
    """
    
    def get_url_status(self, urlkey):
        """
        Get the url status (url, last_version, last_checked), 
        or None if the url data has not been seen before
        """
        c = self.mysql_conn.cursor(MySQLdb.cursors.DictCursor)
        select = "SELECT * FROM url_status WHERE url_hash=%s"
        c.execute(select, urlkey)
        r = c.fetchone()
        return (r['url'], r['last_version'], r['last_checked']) if r else None

    def record_version(self, urlkey, url, parent_key, version, postdata_hash=None):
        """
        Record a version of a page and update the last checked time. 

        If the same version (or None) is passed, the last checked time is still updated.
        """
        now = datetime.now()
        c = self.mysql_conn.cursor(MySQLdb.cursors.DictCursor)
        select = "SELECT * FROM url_status WHERE url_hash=%s"
        c.execute(select, urlkey)
        r = c.fetchone()

        if not r:
            insert = "INSERT INTO url_status (url_hash, url, parent_hash, last_version, last_checked) VALUES (%s,%s,%s,%s,%s)"
            c.execute(insert, (urlkey, url, parent_key, version, now))
        else:
            update = "UPDATE url_status SET last_version=%s, last_checked=%s WHERE url_hash=%s"
            c.execute(update, (version, now, urlkey))
        self.mysql_conn.commit()

        last_version = r['last_version'] if r else None
        if version and version != last_version:
            if not c.execute("SELECT url_hash FROM url_history WHERE version=%s", version):
                insert = "INSERT INTO url_history (url_hash, version, postdata_hash, created) VALUES (%s,%s,%s,%s)"
                c.execute(insert, (urlkey, version, postdata_hash, now))
                self.mysql_conn.commit()

    def get_version_info(self, version):
        """Simple accessor method"""
        c = self.mysql_conn.cursor(MySQLdb.cursors.DictCursor)
        select = "SELECT * FROM url_history WHERE version=%s"
        c.execute(select, version)
        r = c.fetchone()
        return (r['url_hash'], r['created']) if r else None
