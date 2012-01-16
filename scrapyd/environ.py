import os

from zope.interface import implements

from .interfaces import IEnvironment

class Environment(object):

    implements(IEnvironment)

    def __init__(self, config, initenv=os.environ):
        self.dbs_dir = config.get('dbs_dir', 'dbs')
        self.logs_dir = config.get('logs_dir', 'logs')
        self.items_dir = config.get('items_dir', 'items')
        self.jobs_to_keep = config.getint('jobs_to_keep', 5)
        if config.cp.has_section('settings'):
            self.settings = dict(config.cp.items('settings'))
        else:
            self.settings = {}
        self.initenv = initenv

    def get_environment(self, message, slot):
        project = message['_project']
        env = self.initenv.copy()
        env['SCRAPY_SLOT'] = str(slot)
        env['SCRAPY_PROJECT'] = project
        env['SCRAPY_SPIDER'] = message['_spider']
        env['SCRAPY_JOB'] = message['_job']
        if project in self.settings:
            env['SCRAPY_SETTINGS_MODULE'] = self.settings[project]
        dbpath = os.path.join(self.dbs_dir, '%s.db' % project)
        env['SCRAPY_SQLITE_DB'] = dbpath
        env['SCRAPY_LOG_FILE'] = self._get_file(message, self.logs_dir, 'log')
        env['SCRAPY_FEED_URI'] = self._get_file(message, self.items_dir, 'jl')
        return env

    def _get_file(self, message, dir, ext):
        logsdir = os.path.join(dir, message['_project'], \
            message['_spider'])
        if not os.path.exists(logsdir):
            os.makedirs(logsdir)
        to_delete = sorted((os.path.join(logsdir, x) for x in \
            os.listdir(logsdir)), key=os.path.getmtime)[:-self.jobs_to_keep]
        for x in to_delete:
            os.remove(x)
        return os.path.join(logsdir, "%s.%s" % (message['_job'], ext))
