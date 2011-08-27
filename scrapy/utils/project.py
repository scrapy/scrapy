from os.path import join, dirname, abspath, isabs, exists
from os import makedirs, environ
import warnings

from scrapy.utils.conf import closest_scrapy_cfg, get_config
from scrapy.utils.python import is_writable
from scrapy.exceptions import NotConfigured

DATADIR_CFG_SECTION = 'datadir'

def inside_project():
    scrapy_module = environ.get('SCRAPY_SETTINGS_MODULE')
    if scrapy_module is not None:
        try:
            __import__(scrapy_module)
        except ImportError:
            warnings.warn("Cannot import scrapy settings module %s" % scrapy_module)
        else:
            return True
    return bool(closest_scrapy_cfg())

def project_data_dir(project='default'):
    """Return the current project data dir, creating it if it doesn't exist"""
    if not inside_project():
        raise NotConfigured("Not inside a project")
    cfg = get_config()
    if cfg.has_option(DATADIR_CFG_SECTION, project):
        d = cfg.get(DATADIR_CFG_SECTION, project)
    else:
        scrapy_cfg = closest_scrapy_cfg()
        if not scrapy_cfg:
            raise NotConfigured("Unable to find scrapy.cfg file to infer project data dir")
        d = abspath(join(dirname(scrapy_cfg), '.scrapy'))
    if not exists(d):
        makedirs(d)
    return d

def data_path(path):
    """If path is relative, return the given path inside the project data dir,
    otherwise return the path unmodified
    """
    return path if isabs(path) else join(project_data_dir(), path)
