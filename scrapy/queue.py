from twisted.internet import defer

from scrapy.http import Request
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.spider import create_spider_for_request
from scrapy import log


class ExecutionQueue(object):

    def __init__(self, spiders, queue, poll_interval=5, keep_alive=False):
        self.spider_requests = []
        self.poll_interval = poll_interval
        self._spiders = spiders
        self._queue = queue
        self._keepalive = keep_alive

    def _append_next(self):
        """Called when there are no more items left in self.spider_requests.
        This method is meant to be overriden in subclasses to add new (spider,
        requests) tuples to self.spider_requests. It can return a Deferred.
        """
        msg = self._queue.pop()
        if msg:
            name = msg.pop('name')
            self.append_spider_name(name, **msg)

    def get_next(self):
        """Return a tuple (spider, requests) containing a list of Requests and
        the Spider which will be used to crawl those Requests. If there aren't
        any more spiders to crawl it must return (None, []).

        This method can return a deferred.
        """
        if self.spider_requests:
            return self._get_next_now()
        d = defer.maybeDeferred(self._append_next)
        d.addCallback(lambda _: self._get_next_now())
        return d

    def _get_next_now(self):
        try:
            return self.spider_requests.pop(0)
        except IndexError:
            return (None, [])

    def is_finished(self):
        """Return True if the queue is empty and there won't be any more
        spiders to crawl (this is for one-shot runs). If it returns ``False``
        Scrapy will keep polling this queue for new requests to scrape
        """
        return not self._keepalive and not bool(self.spider_requests)

    def append_spider(self, spider):
        """Append a Spider to crawl"""
        requests = spider.start_requests()
        self.spider_requests.append((spider, requests))

    def append_request(self, request, spider=None, **kwargs):
        if spider is None:
            spider = create_spider_for_request(self._spiders, request, **kwargs)
        if spider:
            self.spider_requests.append((spider, [request]))

    def append_url(self, url=None, spider=None, **kwargs):
        """Append a URL to crawl with the given spider. If the spider is not
        given, a spider will be looked up based on the URL
        """
        if url is None:
            raise ValueError("A url is required")
        if spider is None:
            spider = create_spider_for_request(self._spiders, Request(url), \
                **kwargs)
        if spider:
            requests = arg_to_iter(spider.make_requests_from_url(url))
            self.spider_requests.append((spider, requests))

    def append_spider_name(self, name=None, **spider_kwargs):
        """Append a spider to crawl given its name and optional arguments,
        which are used to instantiate it. The SpiderManager is used to lookup
        the spider
        """
        if name is None:
            raise ValueError("A spider name is required")
        try:
            spider = self._spiders.create(name, **spider_kwargs)
        except KeyError:
            log.msg('Unable to find spider: %s' % name, log.ERROR)
        except:
            log.err(None, 'Error creating spider %r with arguments: %r' % \
                (name, spider_kwargs))
        else:
            self.append_spider(spider)
