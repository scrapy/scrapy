import sys
import os
from subprocess import Popen, PIPE
from ConfigParser import NoSectionError

from scrapyd.spiderqueue import SqliteSpiderQueue
from scrapy.utils.python import stringify_dict, unicode_to_str
from scrapyd.config import Config

def get_spider_queues(config):
    """Return a dict of Spider Quees keyed by project name"""
    dbsdir = config.get('dbs_dir', 'dbs')
    if not os.path.exists(dbsdir):
        os.makedirs(dbsdir)
    d = {}
    for project in get_project_list(config):
        dbpath = os.path.join(dbsdir, '%s.db' % project)
        d[project] = SqliteSpiderQueue(dbpath)
    return d

def get_project_list(config):
    """Get list of projects by inspecting the eggs dir and the ones defined in
    the scrapyd.conf [settings] section
    """
    eggs_dir = config.get('eggs_dir', 'eggs')
    if os.path.exists(eggs_dir):
        projects = os.listdir(eggs_dir)
    else:
        projects = []
    try:
        projects += [x[0] for x in config.cp.items('settings')]
    except NoSectionError:
        pass
    return projects

def get_crawl_args(message):
    """Return the command-line arguments to use for the scrapy crawl process
    that will be started for this message
    """
    msg = message.copy()
    args = [unicode_to_str(msg['_spider'])]
    del msg['_project'], msg['_spider']
    settings = msg.pop('settings', {})
    for k, v in stringify_dict(msg, keys_only=False).items():
        args += ['-a']
        args += ['%s=%s' % (k, v)]
    for k, v in stringify_dict(settings, keys_only=False).items():
        args += ['--set']
        args += ['%s=%s' % (k, v)]
    return args

def get_spider_list(project, runner=None):
    """Return the spider list from the given project, using the given runner"""
    if runner is None:
        runner = Config().get('runner')
    env = os.environ.copy()
    env['SCRAPY_PROJECT'] = project
    pargs = [sys.executable, '-m', runner, 'list']
    proc = Popen(pargs, stdout=PIPE, stderr=PIPE, env=env)
    out, err = proc.communicate()
    if proc.returncode:
        msg = err or out or 'unknown error'
        raise RuntimeError(msg.splitlines()[-1])
    return out.splitlines()

