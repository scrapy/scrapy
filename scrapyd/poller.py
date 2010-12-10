from zope.interface import implements
from twisted.internet.defer import DeferredQueue, inlineCallbacks, maybeDeferred, returnValue

from .utils import get_spider_queues
from .interfaces import IPoller

class QueuePoller(object):

    implements(IPoller)

    def __init__(self, config):
        self.config = config
        self.update_projects()
        self.dq = DeferredQueue(size=1)

    @inlineCallbacks
    def poll(self):
        if self.dq.pending:
            return
        for p, q in self.queues.iteritems():
            c = yield maybeDeferred(q.count)
            if c:
                msg = yield maybeDeferred(q.pop)
                returnValue(self.dq.put(self._message(msg, p)))

    def next(self):
        return self.dq.get()

    def update_projects(self):
        self.queues = get_spider_queues(self.config)

    def _message(self, queue_msg, project):
        d = queue_msg.copy()
        d['_project'] = project
        d['_spider'] = d.pop('name')
        return d
