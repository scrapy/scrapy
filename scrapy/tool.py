"""
Scrapy command-line tool
"""

import sys, os
from ConfigParser import RawConfigParser

def closest_scrapy_cfg(path='.', prevpath=None):
    if path == prevpath:
        return ''
    path = os.path.abspath(path)
    cfgfile = os.path.join(path, 'scrapy.cfg')
    if os.path.exists(cfgfile):
        return cfgfile
    return closest_scrapy_cfg(os.path.dirname(path), path)

def main():
    scrapy_cfg = closest_scrapy_cfg()
    cfg_sources = [scrapy_cfg, os.path.expanduser('~/.scrapy.cfg'), '/etc/scrapy.cfg']
    cfg = RawConfigParser()
    cfg.read(cfg_sources)
    if cfg.has_option('default', 'settings'):
        os.environ['SCRAPY_SETTINGS_MODULE'] = cfg.get('default', 'settings')
        projdir = os.path.dirname(scrapy_cfg)
        if projdir not in sys.path:
            sys.path.append(projdir)

    from scrapy.cmdline import execute
    execute()

if __name__ == '__main__':
    main()
