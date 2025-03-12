from scrapy.exceptions import NotConfigured
from scrapy.middleware import MiddlewareManager
from scrapy.utils.test import get_crawler


class M1:
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process(self, response, request, spider):
        pass


class M2:
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass


class M3:
    def process(self, response, request, spider):
        pass


class MOff:
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def __init__(self):
        raise NotConfigured("foo")


class MyMiddlewareManager(MiddlewareManager):
    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return [M1, MOff, M3]

    def _add_middleware(self, mw):
        super()._add_middleware(mw)
        if hasattr(mw, "process"):
            self.methods["process"].append(mw.process)


class TestMiddlewareManager:
    def test_init(self):
        m1, m2, m3 = M1(), M2(), M3()
        mwman = MyMiddlewareManager(m1, m2, m3)
        assert list(mwman.methods["open_spider"]) == [m1.open_spider, m2.open_spider]
        assert list(mwman.methods["close_spider"]) == [m2.close_spider, m1.close_spider]
        assert list(mwman.methods["process"]) == [m1.process, m3.process]

    def test_methods(self):
        mwman = MyMiddlewareManager(M1(), M2(), M3())
        assert [x.__self__.__class__ for x in mwman.methods["open_spider"]] == [M1, M2]
        assert [x.__self__.__class__ for x in mwman.methods["close_spider"]] == [M2, M1]
        assert [x.__self__.__class__ for x in mwman.methods["process"]] == [M1, M3]

    def test_enabled(self):
        m1, m2, m3 = M1(), M2(), M3()
        mwman = MiddlewareManager(m1, m2, m3)
        assert mwman.middlewares == (m1, m2, m3)

    def test_enabled_from_settings(self):
        crawler = get_crawler()
        mwman = MyMiddlewareManager.from_crawler(crawler)
        classes = [x.__class__ for x in mwman.middlewares]
        assert classes == [M1, M3]
