import os
import sys
from operator import itemgetter

import six
from six.moves.configparser import SafeConfigParser

from scrapy.utils.deprecate import update_classpath


def build_component_list(base, custom, convert=update_classpath):
    """Compose a component list based on a custom and base dict of components
    (typically middlewares or extensions), unless custom is already a list, in
    which case it's returned.
    """

    def _check_components(complist):
        if len({convert(c) for c in complist}) != len(complist):
            raise ValueError('Some paths in {!r} convert to the same object, '
                             'please update your settings'.format(complist))

    if isinstance(custom, (list, tuple)):
        _check_components(custom)
        return type(custom)(convert(c) for c in custom)

    def _map_keys(compdict):
        _check_components(compdict)
        return {convert(k): v for k, v in six.iteritems(compdict)}

    compdict = _map_keys(base)
    compdict.update(_map_keys(custom))
    items = (x for x in six.iteritems(compdict) if x[1] is not None)
    return [x[0] for x in sorted(items, key=itemgetter(1))]


def arglist_to_dict(arglist):
    """Convert a list of arguments like ['arg1=val1', 'arg2=val2', ...] to a
    dict
    """
    return dict(x.split('=', 1) for x in arglist)


def closest_scrapy_cfg(path='.', prevpath=None):
    """Return the path to the closest scrapy.cfg file by traversing the current
    directory and its parents
    """
    if path == prevpath:
        return ''
    path = os.path.abspath(path)
    cfgfile = os.path.join(path, 'scrapy.cfg')
    if os.path.exists(cfgfile):
        return cfgfile
    return closest_scrapy_cfg(os.path.dirname(path), path)


def init_env(project='default', set_syspath=True):
    """Initialize environment to use command-line tool from inside a project
    dir. This sets the Scrapy settings module and modifies the Python path to
    be able to locate the project module.
    """
    cfg = get_config()
    if cfg.has_option('settings', project):
        os.environ['SCRAPY_SETTINGS_MODULE'] = cfg.get('settings', project)
    closest = closest_scrapy_cfg()
    if closest:
        projdir = os.path.dirname(closest)
        if set_syspath and projdir not in sys.path:
            sys.path.append(projdir)


def get_config(use_closest=True):
    """Get Scrapy config file as a SafeConfigParser"""
    sources = get_sources(use_closest)
    cfg = SafeConfigParser()
    cfg.read(sources)
    return cfg


def get_sources(use_closest=True):
    xdg_config_home = os.environ.get('XDG_CONFIG_HOME') or \
        os.path.expanduser('~/.config')
    sources = ['/etc/scrapy.cfg', r'c:\scrapy\scrapy.cfg',
               xdg_config_home + '/scrapy.cfg',
               os.path.expanduser('~/.scrapy.cfg')]
    if use_closest:
        sources.append(closest_scrapy_cfg())
    return sources
