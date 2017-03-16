# -*- coding: utf-8 -*-


class BaseExtension(object):
    def engine_started(self):
        pass

    def engine_stopped(self):
        pass

    def spider_opened(self, spider):
        pass

    def spider_idle(self, spider):
        pass

    def spider_closed(self, spider, reason):
        pass

    def spider_error(self, spider, response, failure):
        pass

    def request_scheduled(self, request, spider):
        pass

    def request_dropped(self, request, spider):
        pass

    def response_received(self, response, request, spider):
        pass

    def response_downloaded(self, response, request, spider):
        pass

    def item_scraped(self, item, spider):
        pass

    def item_dropped(self, item, spider, exception):
        pass

    @classmethod
    def from_crawler(cls, crawler):
        pass
