from twisted.trial import unittest

from scrapy.settings import Settings
from scrapy.exceptions import NotConfigured
from scrapy.middleware import MiddlewareManager

class M1(object):

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process(self, response, request, spider):
        pass

class M2(object):

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    pass

class M3(object):

    def process(self, response, request, spider):
        pass


class MOff(object):

    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def __init__(self):
        raise NotConfigured


class TestMiddlewareManager(MiddlewareManager):

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return ['scrapy.tests.test_middleware.%s' % x for x in ['M1', 'MOff', 'M3']]

    def _add_middleware(self, mw):
        super(TestMiddlewareManager, self)._add_middleware(mw)
        if hasattr(mw, 'process'):
            self.methods['process'].append(mw.process)

class MiddlewareManagerTest(unittest.TestCase):

    def test_init(self):
        m1, m2, m3 = M1(), M2(), M3()
        mwman = TestMiddlewareManager(m1, m2, m3)
        self.assertEqual(mwman.methods['open_spider'], [m1.open_spider, m2.open_spider])
        self.assertEqual(mwman.methods['close_spider'], [m2.close_spider, m1.close_spider])
        self.assertEqual(mwman.methods['process'], [m1.process, m3.process])

    def test_methods(self):
        mwman = TestMiddlewareManager(M1(), M2(), M3())
        self.assertEqual([x.im_class for x in mwman.methods['open_spider']],
            [M1, M2])
        self.assertEqual([x.im_class for x in mwman.methods['close_spider']],
            [M2, M1])
        self.assertEqual([x.im_class for x in mwman.methods['process']],
            [M1, M3])

    def test_enabled(self):
        m1, m2, m3 = M1(), M2(), M3()
        mwman = MiddlewareManager(m1, m2, m3)
        self.failUnlessEqual(mwman.middlewares, (m1, m2, m3))

    def test_enabled_from_settings(self):
        settings = Settings()
        mwman = TestMiddlewareManager.from_settings(settings)
        classes = [x.__class__ for x in mwman.middlewares]
        self.failUnlessEqual(classes, [M1, M3])
