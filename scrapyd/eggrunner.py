"""
This module can be used to run a Scrapy project contained in an egg file

To see all spiders in a project:

    python -m scrapyd.eggrunner myproject.egg list

To crawl a spider:

    python -m scrapyd.eggrunner myproject.egg crawl somespider
"""

import sys

from scrapyd.eggutils import activate_egg

def main(eggpath, args):
    """Run scrapy for the settings module name passed"""
    activate_egg(eggpath)
    from scrapy.cmdline import execute
    execute(['scrapy'] + list(args))

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print "usage: %s <eggfile> [scrapy_command args ...]" % sys.argv[0]
        sys.exit(1)
    main(sys.argv[1], sys.argv[2:])
