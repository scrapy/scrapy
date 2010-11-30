import os
from ConfigParser import NoSectionError

from scrapy.spiderqueue import SqliteSpiderQueue
from scrapy.utils.python import stringify_dict, unicode_to_str

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
    args = [unicode_to_str(msg['spider'])]
    del msg['project'], msg['spider']
    for k, v in stringify_dict(msg, keys_only=False).items():
        args += ['-a']
        args += ['%s=%s' % (k, v)]
    return args
