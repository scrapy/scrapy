#!/usr/bin/env python

import os
os.environ.setdefault('SCRAPYSETTINGS_MODULE', 'googledir.settings')

from scrapy.command.cmdline import execute
execute()
