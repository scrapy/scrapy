from zope.interface import implements

from .interfaces import ISpiderScheduler
from .utils import get_spider_queues

class SpiderScheduler(object):

    implements(ISpiderScheduler)

    def __init__(self, config):
        self.eggs_dir = config.get('eggs_dir', 'eggs')
        self.dbs_dir = config.get('dbs_dir', 'dbs')
        self.update_projects()

    def schedule(self, project, spider_name, **spider_args):
        q = self.queues[project]
        q.add(spider_name, **spider_args)

    def list_projects(self):
        return self.queues.keys()

    def update_projects(self):
        self.queues = get_spider_queues(self.eggs_dir, self.dbs_dir)
