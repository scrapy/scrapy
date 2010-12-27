import os

from zope.interface import implements

from .interfaces import IEnvironment

class Environment(object):

    implements(IEnvironment)

    def __init__(self, config, initenv=os.environ):
        self.dbs_dir = config.get('dbs_dir', 'dbs')
        self.logs_dir = config.get('logs_dir', 'logs')
        self.logs_to_keep = config.getint('logs_to_keep', 5)
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
        env['SCRAPY_LOG_FILE'] = self._get_log_file(message)
        return env

    def _get_log_file(self, message):
        logsdir = os.path.join(self.logs_dir, message['_project'], \
            message['_spider'])
        if not os.path.exists(logsdir):
            os.makedirs(logsdir)
        to_delete = sorted(os.listdir(logsdir), reverse=True)[:-self.logs_to_keep]
        for x in to_delete:
            os.remove(os.path.join(logsdir, x))
        return os.path.join(logsdir, "%s.log" % message['_job'])
