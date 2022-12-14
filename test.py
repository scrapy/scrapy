from scrapy.cmdline import execute
import sys

sys.argv = ['scrapy', 'shell', '--set', 'TWISTED_REACTOR=twisted.internet.asyncioreactor.AsyncioSelectorReactor']

execute()
