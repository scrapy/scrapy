import MySQLdb
from twisted.trial import unittest
from datetime import datetime, timedelta
from time import sleep
from scrapy.store.db import DomainDataHistory
from scrapy.utils.db import mysql_connect, parse_uri, URIValidationError
from scrapy.conf import settings

class ConnectionTestCase(unittest.TestCase):
    """ Test connection wrapper """
    test_db = settings.get('TEST_SCRAPING_DB')

    def setUp(self):
        if not self.test_db:
            raise unittest.SkipTest("Missing TEST_SCRAPING_DB setting")

        try:
            mysql_connect(self.test_db)
        except ImportError:
            raise unittest.SkipTest("MySQLdb module not available")
        except MySQLdb.OperationalError:
            raise unittest.SkipTest("Test database not available at: %s" % self.test_db)

    def test_parse_uri(self):
        self.assertRaises(URIValidationError, parse_uri, [self.test_db])
        self.assertRaises(URIValidationError, parse_uri, self.test_db.replace('mysql:', 'gopher:'))

        d = parse_uri(self.test_db)

        self.assertTrue(isinstance(d, dict))
        self.assertTrue(all(key in d for key in ('user', 'host', 'db')))

    def test_mysql_connect(self):
        if not self.test_db:
            raise unittest.SkipTest("Missing TEST_SCRAPING_DB setting")

        self.assertTrue(isinstance(mysql_connect(self.test_db), MySQLdb.connection))
        self.assertTrue(isinstance(mysql_connect(parse_uri(self.test_db)), MySQLdb.connection))

class ProductComparisonTestCase(unittest.TestCase):
    """ Test product comparison functions """
    test_db = settings.get('TEST_SCRAPING_DB')

    def setUp(self):
        if not self.test_db:
            raise unittest.SkipTest("Missing TEST_SCRAPING_DB setting")

        try:
            mysql_connect(self.test_db)
        except ImportError:
            raise unittest.SkipTest("MySQLdb module not available")
        except MySQLdb.OperationalError:
            raise unittest.SkipTest("Test database not available at: %s" % self.test_db)

    def test_domaindatahistory(self):
        ddh = DomainDataHistory(self.test_db, 'domain_data_history')
        c = ddh.mysql_conn.cursor()
        c.execute("DELETE FROM domain_data_history")
        ddh.mysql_conn.commit()

        def now_nomicro():
            now = datetime.now()
            return now - timedelta(microseconds=now.microsecond)

        assert hasattr(ddh.get('scrapy.org'), '__iter__')
        self.assertEqual(list(ddh.get('scrapy.org')), [])

        self.assertEqual(ddh.domain_count(), 0)

        now = now_nomicro()
        ddh.put('scrapy.org', 'value', timestamp=now)
        self.assertEqual(list(ddh.get('scrapy.org')), [(now, 'value')])
        self.assertEqual(list(ddh.get('scrapy2.org')), [])

        sleep(1)
        now2 = now_nomicro()
        ddh.put('scrapy.org', 'newvalue', timestamp=now2)
        self.assertEqual(list(ddh.getall('scrapy.org')), [(now2, 'newvalue'), (now, 'value')])

        self.assertEqual(ddh.getlast('scrapy.org'), (now2, 'newvalue'))
        self.assertEqual(ddh.getlast('scrapy.org', offset=1), (now, 'value'))
        self.assertEqual(ddh.getlast('scrapy2.org'), None)

        ddh.remove('scrapy.org')
        self.assertEqual(list(ddh.get('scrapy.org')), [])

        now3 = now_nomicro()
        d1 = {'name': 'John', 'surname': 'Doe'}
        ddh.put('scrapy.org', d1, timestamp=now3)
        self.assertEqual(list(ddh.getall('scrapy.org')), [(now3, d1)])

        # get path support
        self.assertEqual(ddh.getlast('scrapy.org', path='name'), (now3, 'John'))
        # behaviour for non existant paths
        self.assertEqual(ddh.getlast('scrapy.org', path='name2'), (now3, None))

        self.assertEqual(ddh.domain_count(), 1)

        self.assertEqual(list(ddh.getlast_alldomains()),
                        [('scrapy.org', now3, {'surname': 'Doe', 'name': 'John'})])

if __name__ == "__main__":
    unittest.main()
