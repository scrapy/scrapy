#!/usr/bin/env python

import os
os.environ.setdefault('SCRAPY_SETTINGS_MODULE', '${project_name}.settings')

from scrapy.command.cmdline import execute
execute()
