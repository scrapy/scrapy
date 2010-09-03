import os

from zope.interface import implements

from .interfaces import IEnvironment

class Environment(object):

    implements(IEnvironment)

    def __init__(self, config):
        self.dbs_dir = config.get('dbs_dir', 'dbs')
        self.logs_dir = config.get('logs_dir', 'logs')

    def get_environment(self, message, slot):
        project = message['project']
        env = os.environ.copy()
        env['SCRAPY_PROJECT'] = project
        dbpath = os.path.join(self.dbs_dir, '%s.db' % project)
        env['SCRAPY_SQLITE_DB'] = dbpath
        logpath = os.path.join(self.logs_dir, 'slot%s.log' % slot)
        env['SCRAPY_LOG_FILE'] = logpath
        return env

