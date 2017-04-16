#!/usr/bin/python
#-*-coding:utf-8-*-

from urlparse import urlparse
from scrapy.http import Request
from scrapy.utils.python import WeakKeyCache

class GoogleCacheMiddleware(object):
    """
        this middleware allow spider to crawl the spicific domain url in google caches.

        you can define the GOOGLE_CACHE_DOMAINS in settings,it is a list which you want to visit the 
        google cache.Or you can define a google_cache_domains in your spider and it is as the highest 
        priority.
    """
    google_cache = 'http://webcache.googleusercontent.com/search?q=cache:'

    def __init__(self, cache_domains=''):
        self.cache = WeakKeyCache(self._cache_domains)
        self.cache_domains = cache_domains

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings['GOOGLE_CACHE_DOMAINS'])

    def _cache_domains(self, spider):
        if hasattr(spider, 'google_cache_domains'):
            return spider.google_cache_domains
        elif self.cache_domains:
            return self.cache_domains

        return ""

    def process_request(self, request, spider):
        """
            the scrapy documention said that:
                "If it returns a Request object, the returned request will be rescheduled (in the Scheduler)
                to be downloaded in the future. The callback of the original request will always be called. 
                If the new request has a callback it will be called with the response downloaded, and the 
                output of that callback will then be passed to the original callback. If the new request doesn’t
                have a callback, the response downloaded will be just passed to the original request callback."
             but actually is that if it returns a Request object,then the original request will be droped,so 
             you must make sure that the new request object's callback is the original callback.
        """
        gcd = self.cache[spider]
        if gcd:
            if urlparse(request.url).netloc in gcd:
                request = request.replace(url=self.google_cache + request.url)
                request.meta['google_cache'] = True
                return request
      
    def process_response(self, request, response, spider):

        if request.meta.get('google_cache',False):
            return response.replace(url = response.url[len(self.google_cache):]) 

        return response
