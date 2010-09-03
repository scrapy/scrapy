import os
import pkg_resources

from scrapy.spiderqueue import SqliteSpiderQueue

def get_spider_queues(eggsdir, dbsdir):
    """Return a dict of Spider Quees keyed by project name"""
    d = {}
    for project in os.listdir(eggsdir):
        dbpath = os.path.join(dbsdir, '%s.db' % project)
        d[project] = SqliteSpiderQueue(dbpath)
    return d
