from os.path import join, dirname, abspath, isabs, exists
from os import makedirs
import warnings

from scrapy.utils.conf import closest_scrapy_cfg, get_config
from scrapy.utils.python import is_writable

DATADIR_CFG_SECTION = 'datadir'

def inside_project():
    return bool(closest_scrapy_cfg())

def project_data_dir(project='default'):
    """Return the current project data dir, creating it if it doesn't exist"""
    assert inside_project(), "Not inside project"
    scrapy_cfg = closest_scrapy_cfg()
    d = abspath(join(dirname(scrapy_cfg), '.scrapy'))
    cfg = get_config()
    if cfg.has_option(DATADIR_CFG_SECTION, project):
        d = cfg.get(DATADIR_CFG_SECTION, project)
    if not exists(d):
        makedirs(d)
    return d

def expand_data_path(path):
    """If path is relative, return the given path inside the project data dir,
    otherwise return the path unmodified
    """
    if isabs(path):
        return path
    return join(project_data_dir(), path)

def sqlite_db(path, nonwritable_fallback=True):
    """Get the SQLite database to use. If path is relative, returns the given
    path inside the project data dir, otherwise returns the path unmodified. If
    not inside a project returns :memory: to use an in-memory database.

    If nonwritable_fallback is True, and the path is not writable it issues a
    warning and returns :memory:
    """
    if not inside_project() or path == ':memory:':
        db = ':memory:'
    else:
        db = expand_data_path(path)
        if not is_writable(db) and nonwritable_fallback:
            warnings.warn("%r is not writable - using in-memory SQLite instead" % db)
            db = ':memory:'
    return db
