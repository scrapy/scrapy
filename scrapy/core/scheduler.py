from scrapy.utils.datatypes import PriorityQueue, PriorityStack
from scrapy.utils.misc import load_object
from scrapy.conf import settings

class Scheduler(object):

    def __init__(self):
        self.pending_requests = {}
        self.dfo = settings['SCHEDULER_ORDER'].upper() == 'DFO'
        self.dupefilter = load_object(settings['DUPEFILTER_CLASS'])()

    def spider_is_open(self, spider):
        return spider in self.pending_requests

    def spider_has_pending_requests(self, spider):
        if spider in self.pending_requests:
            return bool(self.pending_requests[spider])

    def open_spider(self, spider):
        if spider in self.pending_requests:
            raise RuntimeError('Scheduler spider already opened: %s' % spider)

        Priority = PriorityStack if self.dfo else PriorityQueue
        self.pending_requests[spider] = Priority()
        return self.dupefilter.open_spider(spider)

    def close_spider(self, spider):
        if spider not in self.pending_requests:
            raise RuntimeError('Scheduler spider is not open: %s' % spider)
        self.pending_requests.pop(spider, None)
        return self.dupefilter.close_spider(spider)

    def enqueue_request(self, spider, request):
        if request.dont_filter or not self.dupefilter.request_seen(spider, request):
            self.pending_requests[spider].push(request, -request.priority)

    def clear_pending_requests(self, spider):
        # TODO: flush queue here or discard enqueued requests, depending on how
        # the spider is being closed.
        pass

    def next_request(self, spider):
        q = self.pending_requests[spider]
        if q:
            return q.pop()[0]

    def is_idle(self):
        return not self.pending_requests
