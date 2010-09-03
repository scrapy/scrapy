from zope.interface import implements
from twisted.internet.defer import DeferredQueue

from .utils import get_spider_queues
from .interfaces import IPoller

class QueuePoller(object):

    implements(IPoller)

    def __init__(self, config):
        self.eggs_dir = config.get('eggs_dir', 'eggs')
        self.dbs_dir = config.get('dbs_dir', 'dbs')
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
        self.queues = get_spider_queues(self.eggs_dir, self.dbs_dir)

    def _message(self, project):
        return {'project': str(project)}
