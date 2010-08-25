import sys
import os
from ConfigParser import RawConfigParser
from operator import itemgetter

def build_component_list(base, custom):
    """Compose a component list based on a custom and base dict of components
    (typically middlewares or extensions), unless custom is already a list, in
    which case it's returned.
    """
    if isinstance(custom, (list, tuple)):
        return custom
    compdict = base.copy()
    compdict.update(custom)
    return [k for k, v in sorted(compdict.items(), key=itemgetter(1)) \
        if v is not None]

def closest_scrapy_cfg(path='.', prevpath=None):
    if path == prevpath:
        return ''
    path = os.path.abspath(path)
    cfgfile = os.path.join(path, 'scrapy.cfg')
    if os.path.exists(cfgfile):
        return cfgfile
    return closest_scrapy_cfg(os.path.dirname(path), path)

def set_scrapy_settings_envvar(project='default', set_syspath=True):
    scrapy_cfg = closest_scrapy_cfg()
    cfg_sources = [scrapy_cfg, os.path.expanduser('~/.scrapy.cfg'), '/etc/scrapy.cfg']
    cfg = RawConfigParser()
    cfg.read(cfg_sources)
    if cfg.has_option(project, 'settings'):
        os.environ['SCRAPY_SETTINGS_MODULE'] = cfg.get(project, 'settings')
        projdir = os.path.dirname(scrapy_cfg)
        if set_syspath and projdir not in sys.path:
            sys.path.append(projdir)
