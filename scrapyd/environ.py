import os

from zope.interface import implements

from .interfaces import IEnvironment

class Environment(object):

    implements(IEnvironment)

    def __init__(self, config, initenv=os.environ):
        self.dbs_dir = config.get('dbs_dir', 'dbs')
        self.logs_dir = config.get('logs_dir', 'logs')
        if config.cp.has_section('settings'):
            self.settings = dict(config.cp.items('settings'))
        else:
            self.settings = {}
        self.initenv = initenv

    def get_environment(self, message, slot, eggpath):
        project = message['project']
        env = self.initenv.copy()
        env['SCRAPY_PROJECT'] = project
        if eggpath:
            env['SCRAPY_EGGFILE'] = eggpath
        elif project in self.settings:
            env['SCRAPY_SETTINGS_MODULE'] = self.settings[project]
        dbpath = os.path.join(self.dbs_dir, '%s.db' % project)
        env['SCRAPY_SQLITE_DB'] = dbpath
        logpath = os.path.join(self.logs_dir, 'slot%s.log' % slot)
        env['SCRAPY_LOG_FILE'] = logpath
        return env

