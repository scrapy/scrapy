from cStringIO import StringIO

from twisted.python import log as txlog, failure
from twisted.trial import unittest

from scrapy import log
from scrapy.spider import Spider
from scrapy.settings import default_settings

class LogTest(unittest.TestCase):

    def test_get_log_level(self):
        default_log_level = getattr(log, default_settings.LOG_LEVEL)
        self.assertEqual(log._get_log_level('WARNING'), log.WARNING)
        self.assertEqual(log._get_log_level(log.WARNING), log.WARNING)
        self.assertRaises(ValueError, log._get_log_level, object())

class ScrapyFileLogObserverTest(unittest.TestCase):

    level = log.INFO
    encoding = 'utf-8'

    def setUp(self):
        self.f = StringIO()
        self.sflo = log.ScrapyFileLogObserver(self.f, self.level, self.encoding)
        self.sflo.start()

    def tearDown(self):
        self.flushLoggedErrors()
        self.sflo.stop()

    def logged(self):
        return self.f.getvalue().strip()[25:]

    def first_log_line(self):
        logged = self.logged()
        return logged.splitlines()[0] if logged else ''

    def test_msg_basic(self):
        log.msg("Hello")
        self.assertEqual(self.logged(), "[scrapy] INFO: Hello")

    def test_msg_spider(self):
        spider = Spider("myspider")
        log.msg("Hello", spider=spider)
        self.assertEqual(self.logged(), "[myspider] INFO: Hello")

    def test_msg_level1(self):
        log.msg("Hello", level=log.WARNING)
        self.assertEqual(self.logged(), "[scrapy] WARNING: Hello")

    def test_msg_level2(self):
        log.msg("Hello", log.WARNING)
        self.assertEqual(self.logged(), "[scrapy] WARNING: Hello")

    def test_msg_wrong_level(self):
        log.msg("Hello", level=9999)
        self.assertEqual(self.logged(), "[scrapy] NOLEVEL: Hello")

    def test_msg_level_spider(self):
        spider = Spider("myspider")
        log.msg("Hello", spider=spider, level=log.WARNING)
        self.assertEqual(self.logged(), "[myspider] WARNING: Hello")

    def test_msg_encoding(self):
        log.msg(u"Price: \xa3100")
        self.assertEqual(self.logged(), "[scrapy] INFO: Price: \xc2\xa3100")

    def test_msg_ignore_level(self):
        log.msg("Hello", level=log.DEBUG)
        log.msg("World", level=log.INFO)
        self.assertEqual(self.logged(), "[scrapy] INFO: World")

    def test_msg_ignore_system(self):
        txlog.msg("Hello")
        self.failIf(self.logged())

    def test_msg_ignore_system_err(self):
        txlog.msg("Hello")
        self.failIf(self.logged())

    def test_err_noargs(self):
        try:
            a = 1/0
        except:
            log.err()
        self.failUnless('Traceback' in self.logged())
        self.failUnless('ZeroDivisionError' in self.logged())

    def test_err_why(self):
        log.err(TypeError("bad type"), "Wrong type")
        self.assertEqual(self.first_log_line(), "[scrapy] ERROR: Wrong type")
        self.failUnless('TypeError' in self.logged())
        self.failUnless('bad type' in self.logged())

    def test_error_outside_scrapy(self):
        """Scrapy logger should still print outside errors"""
        txlog.err(TypeError("bad type"), "Wrong type")
        self.assertEqual(self.first_log_line(), "[-] ERROR: Wrong type")
        self.failUnless('TypeError' in self.logged())
        self.failUnless('bad type' in self.logged())

# this test fails in twisted trial observer, not in scrapy observer
#    def test_err_why_encoding(self):
#        log.err(TypeError("bad type"), u"\xa3")
#        self.assertEqual(self.first_log_line(), "[scrapy] ERROR: \xc2\xa3")

    def test_err_exc(self):
        log.err(TypeError("bad type"))
        self.failUnless('Unhandled Error' in self.logged())
        self.failUnless('TypeError' in self.logged())
        self.failUnless('bad type' in self.logged())

    def test_err_failure(self):
        log.err(failure.Failure(TypeError("bad type")))
        self.failUnless('Unhandled Error' in self.logged())
        self.failUnless('TypeError' in self.logged())
        self.failUnless('bad type' in self.logged())


class Latin1ScrapyFileLogObserverTest(ScrapyFileLogObserverTest):

    encoding = 'latin-1'

    def test_msg_encoding(self):
        log.msg(u"Price: \xa3100")
        logged = self.f.getvalue().strip()[25:]
        self.assertEqual(self.logged(), "[scrapy] INFO: Price: \xa3100")

# this test fails in twisted trial observer, not in scrapy observer
#    def test_err_why_encoding(self):
#        log.err(TypeError("bad type"), u"\xa3")
#        self.assertEqual(self.first_log_line(), "[scrapy] ERROR: \xa3")


if __name__ == "__main__":
    unittest.main()
