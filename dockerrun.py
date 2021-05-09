from scrapy.cmdline import execute
from os import chdir

"""
Example of how to run a spider previously created with scrapy's tutorial

chdir("./tutorial")
execute(["scrapy", "crawl", "quotes"])
"""