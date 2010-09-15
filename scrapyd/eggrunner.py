import os

from scrapyd.eggutils import activate_egg

eggpath = os.environ.get('SCRAPY_EGGFILE')
if eggpath:
    activate_egg(eggpath)
from scrapy.cmdline import execute
execute()
