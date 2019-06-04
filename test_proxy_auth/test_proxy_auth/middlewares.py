# -*- coding: utf-8 -*-
import random
import logging

from scrapy import signals


class ProxyMiddleware(object):
    test_ip = ['http://user1:pwd1@123.123.123.123:123', 'http://user2:pwd2@234.234.234.234:234']
    num = 0

    def process_request(self, request, spider):
        request.meta['proxy'] = random.choice(self.test_ip)
        spider.logger.info('use the proxy is ' + str(request.meta.get('proxy', 'no proxy')))
        #spider.logger.info(request.headers)
        spider.logger.info('retry %d times '%self.num + 'and the request.headers is ' + str(request.headers))

        self.num += 1

