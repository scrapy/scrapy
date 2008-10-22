from datetime import datetime, timedelta
from time import sleep

from twisted.trial import unittest
from scrapy.conf import settings


class ProductComparisonTestCase(unittest.TestCase):
    """ Test product comparison functions """
    
    def setUp(self):
        self.test_db = settings.get('TEST_SCRAPING_DB')
        if not self.test_db:
            raise unittest.SkipTest("Missing TEST_SCRAPING_DB setting")

        try:
            import MySQLdb
            from scrapy.utils.db import mysql_connect
            mysql_connect(self.test_db)
        except ImportError:
            raise unittest.SkipTest("MySQLdb module not available")
        except MySQLdb.OperationalError:
            raise unittest.SkipTest("Test database not available at: %s" % self.test_db)

    def test_domaindatahistory(self):
        from scrapy.store.db import DomainDataHistory
        from time import sleep

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
