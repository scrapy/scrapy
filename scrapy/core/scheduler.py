from scrapy.utils.datatypes import PriorityQueue, PriorityStack
from scrapy.utils.misc import load_object

class Scheduler(object):

    def __init__(self, dupefilter, dfo=False):
        self.dupefilter = dupefilter
        Queue = PriorityStack if dfo else PriorityQueue
        self.pending_requests = Queue()

    @classmethod
    def from_settings(cls, settings):
        dfo = settings['SCHEDULER_ORDER'].upper() == 'DFO'
        dupefilter_cls = load_object(settings['DUPEFILTER_CLASS'])
        dupefilter = dupefilter_cls.from_settings(settings)
        return cls(dupefilter, dfo=dfo)

    def has_pending_requests(self):
        return bool(self.pending_requests)

    def enqueue_request(self, request):
        if request.dont_filter or not self.dupefilter.request_seen(request):
            self.pending_requests.push(request, -request.priority)

    def next_request(self):
        if self.pending_requests:
            return self.pending_requests.pop()[0]

    def open(self, spider):
        pass

    def close(self, reason):
        pass
