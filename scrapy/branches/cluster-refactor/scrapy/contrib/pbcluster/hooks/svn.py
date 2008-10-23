""" 
This module contains hooks for updating code via svn. Useful for running before
starting to crawl a domain, for example to update spider code 
"""

import pysvn

from scrapy.conf import settings
from scrapy import log

SVN_DIR = settings['SVN_DIR']
SVN_USER = settings['SVN_USER']
SVN_PASS = settings['SVN_PASS']

def svnup(domain, spider_settings):
    c = pysvn.Client()
    c.callback_get_login = lambda x,y,z: (True, SVN_USER, SVN_PASS, False)
    try:
        r = c.update(SVN_DIR)
        log.msg("ClusterWorker: SVN code updated to revision %s (triggered by domain %s)" % \
                (r[0].number, domain), level=log.DEBUG)
    except pysvn.ClientError, e:
        log.msg("ClusterWorker: unable to update svn code - %s" % e, level=log.WARNING)
