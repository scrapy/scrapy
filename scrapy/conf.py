"""
Scrapy settings manager

See documentation in docs/topics/settings.rst
"""

import os
import cPickle as pickle

from scrapy.settings import CrawlerSettings
from scrapy.utils.conf import init_env

ENVVAR = 'SCRAPY_SETTINGS_MODULE'

def get_project_settings():
    if ENVVAR not in os.environ:
        project = os.environ.get('SCRAPY_PROJECT', 'default')
        init_env(project)
    settings_module_path = os.environ.get(ENVVAR, 'scrapy_settings')
    try:
        settings_module = __import__(settings_module_path, {}, {}, [''])
    except ImportError:
        settings_module = None
    settings = CrawlerSettings(settings_module)

    # XXX: remove this hack
    pickled_settings = os.environ.get("SCRAPY_PICKLED_SETTINGS_TO_OVERRIDE")
    settings.overrides = pickle.loads(pickled_settings) if pickled_settings else {}

    # XXX: deprecate and remove this functionality
    for k, v in os.environ.items():
        if k.startswith('SCRAPY_'):
            settings.overrides[k[7:]] = v

    return settings

settings = get_project_settings()
