from zope.interface import implements
from twisted.internet.defer import DeferredQueue

from .utils import get_spider_queues
from .interfaces import IPoller

class QueuePoller(object):

    implements(IPoller)

    def __init__(self, config):
        self.config = config
        self.update_projects()
        self.dq = DeferredQueue(size=1)

    def poll(self):
        if self.dq.pending:
            return
        for p, q in self.queues.iteritems():
            if q.count():
                return self.dq.put(self._message(p))

    def next(self):
        return self.dq.get()

    def update_projects(self):
        self.queues = get_spider_queues(self.config)

    def _message(self, project):
        return {'project': str(project)}
