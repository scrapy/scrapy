"""This module can be used to execute Scrapyd from a Scrapy command"""

import sys
import os
from cStringIO import StringIO

from twisted.python import log
from twisted.internet import reactor
from twisted.application import app

from scrapy.utils.project import project_data_dir

from scrapyd import get_application
from scrapyd.config import Config

def _get_config():
    datadir = os.path.join(project_data_dir(), 'scrapyd')
    conf = {
        'eggs_dir': os.path.join(datadir, 'eggs'),
        'logs_dir': os.path.join(datadir, 'logs'),
        'items_dir': os.path.join(datadir, 'items'),
        'dbs_dir': os.path.join(datadir, 'dbs'),
    }
    for k in ['eggs_dir', 'logs_dir', 'items_dir', 'dbs_dir']: # create dirs
        d = conf[k]
        if not os.path.exists(d):
            os.makedirs(d)
    scrapyd_conf = """
[scrapyd]
eggs_dir = %(eggs_dir)s
logs_dir = %(logs_dir)s
items_dir = %(items_dir)s
dbs_dir  = %(dbs_dir)s
    """ % conf
    return Config(extra_sources=[StringIO(scrapyd_conf)])

def execute():
    config = _get_config()
    log.startLogging(sys.stderr)
    application = get_application(config)
    app.startApplication(application, False)
    reactor.run()
